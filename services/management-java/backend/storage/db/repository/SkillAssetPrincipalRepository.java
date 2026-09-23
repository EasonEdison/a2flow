package dev.a2flow.management.storage.db.repository;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import dev.a2flow.management.access.AssetPrincipalRole;
import dev.a2flow.management.access.AssetPrincipalStatus;
import dev.a2flow.management.access.AssetPrincipalType;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.storage.db.entity.SkillAssetPrincipalDO;
import dev.a2flow.management.storage.db.mapper.SkillAssetPrincipalMapper;
import dev.a2flow.management.storage.db.mapper.SkillFactoryMapperConstants;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 通用资产成员 Repository。
 *
 * <p>该类是 {@code skill_asset_principal} 的唯一数据访问边界。它提供 ACTIVE OWNER 查询和完整集合
 * 替换，不读取 Skill/组件领域表中的 owner 字符串，也不在数据库异常时退化成全员可编辑。
 */
@Repository
@Slf4j
public class SkillAssetPrincipalRepository {

    public static final String NAMESPACE_SKILL_FACTORY = "SKILL_FACTORY";

    private static final String EMPTY_JSON_OBJECT = "{}";
    private static final String SAFE_PRINCIPAL_PATTERN = "[A-Za-z0-9._-]+";
    private static final String ERROR_OWNER_REQUIRED = "asset owner is required";
    private static final String ERROR_OWNER_INVALID = "asset owner is invalid";
    private static final String ERROR_REPLACE_FAILED = "replace asset owners failed";
    private static final String ERROR_ASSET_IDENTITY_REQUIRED = "asset identity is required";

    @Resource
    private SkillAssetPrincipalMapper skillAssetPrincipalMapper;

    /**
     * 查询某个稳定资产的 ACTIVE OWNER 集合。
     */
    public List<SkillAssetPrincipalDO> listActiveOwners(ReleaseAssetType assetType, String assetKey) {
        validateIdentity(assetType, assetKey);
        List<SkillAssetPrincipalDO> result = skillAssetPrincipalMapper.selectList(
                        ownerWrapper(assetType, assetKey)
                                .eq(SkillAssetPrincipalDO::getStatus, AssetPrincipalStatus.ACTIVE.name())
                                .orderByAsc(SkillAssetPrincipalDO::getPrincipalId))
                .stream()
                .map(this::copy)
                .collect(Collectors.toList());
        log.info("SkillFactory查询资产负责人完成, assetType:{}, assetKey:{}, ownerCount:{}",
                assetType, assetKey, result.size());
        return result;
    }

    /**
     * 批量查询同一资产类型下多个稳定资产的 ACTIVE OWNER。
     *
     * <p>该入口用于列表页一次加载负责人投影，避免逐条调用单资产查询产生 N+1。返回 Map 仅包含
     * 实际命中的资产；调用方不得把未命中资产解释为全员可编辑。
     */
    public Map<String, List<SkillAssetPrincipalDO>> listActiveOwnersByAssetKeys(
            ReleaseAssetType assetType, List<String> assetKeys) {
        if (assetType == null) {
            throw new IllegalArgumentException(ERROR_ASSET_IDENTITY_REQUIRED);
        }
        List<String> normalizedKeys = assetKeys == null ? Collections.emptyList() : assetKeys.stream()
                .map(StringUtils::trimToEmpty)
                .filter(StringUtils::isNotBlank)
                .distinct()
                .collect(Collectors.toList());
        if (normalizedKeys.isEmpty()) {
            return Collections.emptyMap();
        }
        List<SkillAssetPrincipalDO> rows = skillAssetPrincipalMapper.selectList(
                new LambdaQueryWrapper<SkillAssetPrincipalDO>()
                        .eq(SkillAssetPrincipalDO::getNamespace, NAMESPACE_SKILL_FACTORY)
                        .eq(SkillAssetPrincipalDO::getAssetType, assetType.name())
                        .in(SkillAssetPrincipalDO::getAssetKey, normalizedKeys)
                        .eq(SkillAssetPrincipalDO::getPrincipalType, AssetPrincipalType.USER.name())
                        .eq(SkillAssetPrincipalDO::getRoleType, AssetPrincipalRole.OWNER.name())
                        .eq(SkillAssetPrincipalDO::getStatus, AssetPrincipalStatus.ACTIVE.name())
                        .orderByAsc(SkillAssetPrincipalDO::getAssetKey)
                        .orderByAsc(SkillAssetPrincipalDO::getPrincipalId));
        Map<String, List<SkillAssetPrincipalDO>> result = new LinkedHashMap<>();
        if (rows != null) {
            for (SkillAssetPrincipalDO row : rows) {
                result.computeIfAbsent(row.getAssetKey(), ignored -> new ArrayList<>())
                        .add(copy(row));
            }
        }
        log.info("SkillFactory批量查询资产负责人完成, assetType:{}, assetCount:{}, matchedAssetCount:{}",
                assetType, normalizedKeys.size(), result.size());
        return result;
    }

    /**
     * 判断某用户是否是资产的 ACTIVE OWNER。
     */
    public boolean isActiveOwner(ReleaseAssetType assetType, String assetKey, String principalId) {
        if (StringUtils.isBlank(principalId)) {
            return false;
        }
        Long count = skillAssetPrincipalMapper.selectCount(
                ownerWrapper(assetType, assetKey)
                        .eq(SkillAssetPrincipalDO::getPrincipalId, principalId)
                        .eq(SkillAssetPrincipalDO::getStatus, AssetPrincipalStatus.ACTIVE.name()));
        return count != null && count > 0;
    }

    /**
     * 完整替换资产负责人集合。
     *
     * <p>目标集合不能为空；同一 sellerDataManager 短事务内激活目标负责人、禁用其余负责人并插入缺失关系。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public List<SkillAssetPrincipalDO> replaceOwners(ReleaseAssetType assetType, String assetKey,
            List<String> ownerIds, String operator) {
        validateIdentity(assetType, assetKey);
        List<String> normalizedOwners = normalizeOwners(ownerIds);
        List<SkillAssetPrincipalDO> existing = skillAssetPrincipalMapper.selectList(
                ownerWrapper(assetType, assetKey));
        long now = System.currentTimeMillis();
        Set<String> existingIds = new LinkedHashSet<>();
        for (SkillAssetPrincipalDO principalDO : existing) {
            existingIds.add(principalDO.getPrincipalId());
            String targetStatus = normalizedOwners.contains(principalDO.getPrincipalId())
                                  ? AssetPrincipalStatus.ACTIVE.name()
                                  : AssetPrincipalStatus.DISABLED.name();
            int rows = skillAssetPrincipalMapper.update(null,
                    new LambdaUpdateWrapper<SkillAssetPrincipalDO>()
                            .eq(SkillAssetPrincipalDO::getId, principalDO.getId())
                            .set(SkillAssetPrincipalDO::getStatus, targetStatus)
                            .set(SkillAssetPrincipalDO::getModifier, operator)
                            .set(SkillAssetPrincipalDO::getUpdateTime, now));
            if (rows <= 0) {
                throw new IllegalStateException(ERROR_REPLACE_FAILED);
            }
        }
        for (String ownerId : normalizedOwners) {
            if (existingIds.contains(ownerId)) {
                continue;
            }
            SkillAssetPrincipalDO principalDO = new SkillAssetPrincipalDO()
                    .setNamespace(NAMESPACE_SKILL_FACTORY)
                    .setAssetType(assetType.name())
                    .setAssetKey(assetKey)
                    .setPrincipalType(AssetPrincipalType.USER.name())
                    .setPrincipalId(ownerId)
                    .setRoleType(AssetPrincipalRole.OWNER.name())
                    .setStatus(AssetPrincipalStatus.ACTIVE.name())
                    .setAttribute(EMPTY_JSON_OBJECT)
                    .setCreator(operator)
                    .setModifier(operator)
                    .setCreateTime(now)
                    .setUpdateTime(now);
            if (skillAssetPrincipalMapper.insert(principalDO) <= 0) {
                throw new IllegalStateException(ERROR_REPLACE_FAILED);
            }
        }
        List<SkillAssetPrincipalDO> saved = listActiveOwners(assetType, assetKey);
        if (saved.isEmpty()) {
            throw new IllegalStateException(ERROR_OWNER_REQUIRED);
        }
        log.info("SkillFactory完整替换资产负责人完成, assetType:{}, assetKey:{}, ownerCount:{}, operator:{}",
                assetType, assetKey, saved.size(), operator);
        return saved;
    }

    private LambdaQueryWrapper<SkillAssetPrincipalDO> ownerWrapper(
            ReleaseAssetType assetType, String assetKey) {
        return new LambdaQueryWrapper<SkillAssetPrincipalDO>()
                .eq(SkillAssetPrincipalDO::getNamespace, NAMESPACE_SKILL_FACTORY)
                .eq(SkillAssetPrincipalDO::getAssetType, assetType.name())
                .eq(SkillAssetPrincipalDO::getAssetKey, assetKey)
                .eq(SkillAssetPrincipalDO::getPrincipalType, AssetPrincipalType.USER.name())
                .eq(SkillAssetPrincipalDO::getRoleType, AssetPrincipalRole.OWNER.name());
    }

    private List<String> normalizeOwners(List<String> ownerIds) {
        Set<String> result = new LinkedHashSet<>();
        if (ownerIds != null) {
            for (String ownerId : ownerIds) {
                String normalized = StringUtils.trimToEmpty(ownerId);
                if (StringUtils.isBlank(normalized) || !normalized.matches(SAFE_PRINCIPAL_PATTERN)) {
                    throw new IllegalArgumentException(ERROR_OWNER_INVALID);
                }
                result.add(normalized);
            }
        }
        if (result.isEmpty()) {
            throw new IllegalArgumentException(ERROR_OWNER_REQUIRED);
        }
        return new ArrayList<>(result);
    }

    private void validateIdentity(ReleaseAssetType assetType, String assetKey) {
        if (assetType == null || StringUtils.isBlank(assetKey)) {
            throw new IllegalArgumentException(ERROR_ASSET_IDENTITY_REQUIRED);
        }
    }

    private SkillAssetPrincipalDO copy(SkillAssetPrincipalDO source) {
        return new SkillAssetPrincipalDO()
                .setId(source.getId())
                .setNamespace(source.getNamespace())
                .setAssetType(source.getAssetType())
                .setAssetKey(source.getAssetKey())
                .setPrincipalType(source.getPrincipalType())
                .setPrincipalId(source.getPrincipalId())
                .setRoleType(source.getRoleType())
                .setStatus(source.getStatus())
                .setAttribute(source.getAttribute())
                .setCreator(source.getCreator())
                .setModifier(source.getModifier())
                .setCreateTime(source.getCreateTime())
                .setUpdateTime(source.getUpdateTime());
    }
}
