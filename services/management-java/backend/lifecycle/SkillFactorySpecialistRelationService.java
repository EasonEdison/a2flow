package dev.a2flow.management.lifecycle;

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
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.model.SkillFactoryEntityRelationConstants;
import dev.a2flow.management.storage.db.entity.EntityRelationDO;
import dev.a2flow.management.storage.db.repository.EntityRelationRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 所属专员关系领域服务。
 *
 * <p>该服务把页面 KConf 中受控的专员配置转换为 `entity_relation` 版本关系，并为列表、详情和发布
 * 提供统一读取投影。所属专员不再写入 `skill_draft`，关系版本直接使用 Skill 当前数字版本，因此
 * 新建变更和重置基线可以复用通用关系复制能力，不需要额外维护专员快照字段。
 */
@Service
@Slf4j
public class SkillFactorySpecialistRelationService {

    private static final String FIELD_ID = "id";
    private static final String FIELD_NAME = "name";
    private static final String FIELD_SPECIALIST_ID = "specialistId";
    private static final String FIELD_SPECIALIST_NAME = "specialistName";
    private static final String COMMA = ",";
    private static final String ERROR_DRAFT_ID_REQUIRED = "Skill草稿缺少稳定主键";
    private static final String ERROR_SPECIALIST_REQUIRED = "所属专员不能为空";
    private static final String ERROR_SPECIALIST_CONFIG_INVALID = "所属专员配置不完整";
    private static final String ERROR_SPECIALIST_SNAPSHOT_INVALID = "所属专员关系快照格式不合法";

    @Resource
    private SkillFactoryPageConfigService pageConfigService;

    @Resource
    private EntityRelationRepository entityRelationRepository;

    /**
     * 在创建目录和草稿前校验所属专员。
     *
     * <p>注册入口先执行本方法，保证请求专员缺失或未配置时不会留下半成品 workspace。
     */
    public void validateSpecialists(String requestedSpecialistIds) {
        if (pageConfigService.resolveSpecialists(requestedSpecialistIds).isEmpty()) {
            throw new IllegalArgumentException(ERROR_SPECIALIST_REQUIRED);
        }
    }

    /**
     * 注册 Skill 时写入当前版本的完整所属专员关系。
     *
     * <p>请求只提供专员 ID，专员名称始终从后端 KConf 配置读取，避免客户端伪造展示名。该方法会保留
     * 当前版本下其他关系类型，只覆盖所属专员关系。
     */
    public List<Map<String, Object>> replaceSpecialists(SkillDraft draft, String requestedSpecialistIds,
            String operator) {
        requireDraftIdentity(draft);
        List<Map<String, Object>> specialists = pageConfigService.resolveSpecialists(requestedSpecialistIds);
        if (specialists.isEmpty()) {
            throw new IllegalArgumentException(ERROR_SPECIALIST_REQUIRED);
        }
        List<EntityRelationDO> allRelations = allRelations(draft);
        List<EntityRelationDO> targetRelations = allRelations.stream()
                .filter(relation -> !StringUtils.equals(
                        SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_BELONGS_TO_SPECIALIST,
                        relation.getRelationType()))
                .collect(Collectors.toCollection(ArrayList::new));
        targetRelations.addAll(specialists.stream()
                .map(this::toSpecialistRelation)
                .collect(Collectors.toList()));
        entityRelationRepository.replaceBySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_SKILL,
                sourceEntityId(draft), draft.getVersion(), targetRelations, operator);
        log.info("SkillFactory所属专员关系覆盖完成, skillCode:{}, skillVersion:{}, specialistCount:{}, "
                        + "operator:{}",
                draft.getSkillCode(), draft.getVersion(), specialists.size(), operator);
        return specialists;
    }

    /**
     * 查询当前 Skill 版本绑定的所属专员受控快照。
     */
    public List<Map<String, Object>> listSpecialists(SkillDraft draft) {
        if (draft == null || draft.getId() == null || draft.getVersion() == null) {
            return Collections.emptyList();
        }
        return specialistSnapshots(allRelations(draft));
    }

    /** 单项与批量查询共用快照解析及字段补全，非法快照仍明确失败。 */
    private List<Map<String, Object>> specialistSnapshots(List<EntityRelationDO> relations) {
        List<Map<String, Object>> specialists = new ArrayList<>();
        for (EntityRelationDO relation : relations) {
            if (!StringUtils.equals(
                    SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_BELONGS_TO_SPECIALIST,
                    relation.getRelationType())) {
                continue;
            }
            Map<String, Object> snapshot = parseSnapshot(relation);
            snapshot.putIfAbsent(FIELD_SPECIALIST_ID, relation.getTargetEntityId());
            snapshot.putIfAbsent(FIELD_SPECIALIST_NAME, relation.getTargetEntityCode());
            specialists.add(snapshot);
        }
        return specialists;
    }

    /**
     * 返回发布侧需要的专员 ID 集合。
     */
    public List<String> specialistIds(SkillDraft draft) {
        return specialistIdsFromSnapshots(listSpecialists(draft));
    }

    /** 按一页当前草稿的精确主键/版本批量读取专员，返回以草稿主键索引的同口径 ID 集合。 */
    public Map<Long, List<String>> specialistIdsByDrafts(List<SkillDraft> drafts) {
        Map<String, Integer> versions = new LinkedHashMap<>();
        for (SkillDraft draft : drafts) {
            if (draft == null || draft.getId() == null || draft.getVersion() == null) {
                continue;
            }
            versions.put(sourceEntityId(draft), draft.getVersion());
        }
        List<EntityRelationDO> relations = entityRelationRepository.listBySourceVersions(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_SKILL, versions,
                SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_BELONGS_TO_SPECIALIST);
        Map<String, List<EntityRelationDO>> bySource = relations.stream()
                .collect(Collectors.groupingBy(EntityRelationDO::getSourceEntityId));
        Map<Long, List<String>> result = new LinkedHashMap<>();
        versions.forEach((sourceId, version) -> result.put(Long.valueOf(sourceId),
                specialistIdsFromSnapshots(specialistSnapshots(
                        bySource.getOrDefault(sourceId, Collections.emptyList())))));
        log.info("SkillFactory批量投影当前草稿专员完成, draftCount:{}, relationCount:{}",
                versions.size(), relations.size());
        return result;
    }

    private List<String> specialistIdsFromSnapshots(List<Map<String, Object>> specialists) {
        Set<String> ids = new LinkedHashSet<>();
        for (Map<String, Object> specialist : specialists) {
            String id = StringUtils.trimToEmpty(String.valueOf(
                    specialist.getOrDefault(FIELD_SPECIALIST_ID, specialist.get(FIELD_ID))));
            if (StringUtils.isNotBlank(id)) {
                ids.add(id);
            }
        }
        return new ArrayList<>(ids);
    }

    /**
     * 把专员关系转换为兼容现有页面接口的逗号分隔字段。
     */
    public void putPageProjection(Map<String, Object> target, SkillDraft draft) {
        List<Map<String, Object>> specialists = listSpecialists(draft);
        target.put(FIELD_SPECIALIST_ID, joinField(specialists, FIELD_SPECIALIST_ID, FIELD_ID));
        target.put(FIELD_SPECIALIST_NAME, joinField(specialists, FIELD_SPECIALIST_NAME, FIELD_NAME));
    }

    /** 判断 Skill 主记录或所属专员关系是否命中列表搜索关键字。 */
    public boolean matchesKeyword(SkillDraft draft, String keyword) {
        if (StringUtils.isBlank(keyword)) {
            return true;
        }
        if (draft != null && (StringUtils.containsIgnoreCase(draft.getSkillCode(), keyword)
                || StringUtils.containsIgnoreCase(draft.getSkillNameCn(), keyword)
                || StringUtils.containsIgnoreCase(draft.getSkillNameEn(), keyword)
                || StringUtils.containsIgnoreCase(draft.getSkillDescription(), keyword)
                || StringUtils.containsIgnoreCase(draft.getBusinessDomain(), keyword)
                || StringUtils.containsIgnoreCase(draft.getCapabilityDomain(), keyword)
                || StringUtils.containsIgnoreCase(draft.getOwner(), keyword))) {
            return true;
        }
        for (Map<String, Object> specialist : listSpecialists(draft)) {
            if (StringUtils.containsIgnoreCase(String.valueOf(specialist.get(FIELD_SPECIALIST_ID)), keyword)
                    || StringUtils.containsIgnoreCase(
                            String.valueOf(specialist.get(FIELD_SPECIALIST_NAME)), keyword)) {
                return true;
            }
        }
        return false;
    }

    private List<EntityRelationDO> allRelations(SkillDraft draft) {
        return entityRelationRepository.listBySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_SKILL,
                sourceEntityId(draft), draft.getVersion());
    }

    private EntityRelationDO toSpecialistRelation(Map<String, Object> specialist) {
        String specialistId = mapString(specialist, FIELD_ID);
        String specialistName = mapString(specialist, FIELD_NAME);
        if (StringUtils.isAnyBlank(specialistId, specialistName)) {
            throw new IllegalArgumentException(ERROR_SPECIALIST_CONFIG_INVALID);
        }
        Map<String, Object> snapshot = new LinkedHashMap<>();
        snapshot.put(FIELD_SPECIALIST_ID, specialistId);
        snapshot.put(FIELD_SPECIALIST_NAME, specialistName);
        return new EntityRelationDO()
                .setRelationType(
                        SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_BELONGS_TO_SPECIALIST)
                .setTargetEntityType(SkillFactoryEntityRelationConstants.ENTITY_TYPE_SPECIALIST)
                .setTargetEntityId(specialistId)
                .setTargetEntityCode(specialistId)
                .setTargetVersion(StringUtils.EMPTY)
                .setRelationMode(SkillFactoryEntityRelationConstants.RELATION_MODE_ASSIGNED)
                .setSnapshotJson(JsonSupport.toJSON(snapshot));
    }

    /** 安全读取专员配置字段，避免 null 被转换成字符串字面量。 */
    private String mapString(Map<String, Object> source, String field) {
        if (source == null || source.get(field) == null) {
            return StringUtils.EMPTY;
        }
        return StringUtils.trimToEmpty(String.valueOf(source.get(field)));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseSnapshot(EntityRelationDO relation) {
        try {
            Object parsed = JsonSupport.fromJSON(relation.getSnapshotJson(), Object.class);
            if (parsed instanceof Map) {
                return new LinkedHashMap<>((Map<String, Object>) parsed);
            }
        } catch (Exception exception) {
            log.warn("SkillFactory所属专员关系快照解析失败, relationId:{}, targetEntityId:{}, error:{}",
                    relation.getId(), relation.getTargetEntityId(), exception.getMessage());
            throw new IllegalStateException(ERROR_SPECIALIST_SNAPSHOT_INVALID, exception);
        }
        log.warn("SkillFactory所属专员关系快照不是JSON对象, relationId:{}, targetEntityId:{}",
                relation.getId(), relation.getTargetEntityId());
        throw new IllegalStateException(ERROR_SPECIALIST_SNAPSHOT_INVALID);
    }

    private String joinField(List<Map<String, Object>> specialists, String primaryField, String fallbackField) {
        return specialists.stream()
                .map(item -> item.getOrDefault(primaryField, item.get(fallbackField)))
                .filter(java.util.Objects::nonNull)
                .map(String::valueOf)
                .map(StringUtils::trimToEmpty)
                .filter(StringUtils::isNotBlank)
                .collect(Collectors.joining(COMMA));
    }

    private String sourceEntityId(SkillDraft draft) {
        requireDraftIdentity(draft);
        return String.valueOf(draft.getId());
    }

    private void requireDraftIdentity(SkillDraft draft) {
        if (draft == null || draft.getId() == null || draft.getId() <= 0L
                || draft.getVersion() == null || draft.getVersion() <= 0) {
            throw new IllegalStateException(ERROR_DRAFT_ID_REQUIRED);
        }
    }
}
