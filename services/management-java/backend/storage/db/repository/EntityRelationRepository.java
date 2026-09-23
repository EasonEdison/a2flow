package dev.a2flow.management.storage.db.repository;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import dev.a2flow.management.storage.db.entity.EntityRelationDO;
import dev.a2flow.management.storage.db.mapper.EntityRelationMapper;
import dev.a2flow.management.storage.db.mapper.SkillFactoryMapperConstants;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 通用实体关系 Repository。
 *
 * <p>该类是 `entity_relation` 的唯一数据访问入口。上游 Service 负责校验 Skill 版本、
 * 解析能力/组件事实并组装受控快照；本类只负责通过 Mapper 按
 * `sourceEntityId + sourceVersion` 查询、完整集合覆盖和版本复制。它不维护 `SET_HEAD`、
 * 独立 relation revision，也不决定某个关系是否允许发布或执行。
 */
@Repository
@Slf4j
public class EntityRelationRepository {

    private static final String SAFE_ID_PATTERN = "[A-Za-z0-9._-]+";
    private static final String EMPTY_JSON_OBJECT = "{}";
    private static final String ERROR_SOURCE_IDENTITY_INVALID = "entity relation source identity is invalid";
    private static final String ERROR_SOURCE_VERSION_INVALID = "entity relation source version is invalid";
    private static final String ERROR_TARGET_INVALID = "entity relation target is invalid";
    private static final String ERROR_REPLACE_FAILED = "replace entity relations failed";
    private static final int INITIAL_SORT_NO = 0;
    private static final int SOURCE_BATCH_LIMIT = 100;
    private static final String ERROR_SOURCE_BATCH_INVALID = "entity relation source batch is invalid";

    @Resource
    private EntityRelationMapper entityRelationMapper;

    /**
     * 按源实体和源版本读取完整关系集合。
     */
    public List<EntityRelationDO> listBySourceVersion(String namespace, String sourceEntityType,
            String sourceEntityId, int sourceVersion) {
        validateSourceIdentity(namespace, sourceEntityType, sourceEntityId, sourceVersion);
        List<EntityRelationDO> relations =
                listBySourceVersionDb(namespace, sourceEntityType, sourceEntityId, sourceVersion);
        log.info("SkillFactory查询实体关系完成, namespace:{}, sourceEntityType:{}, sourceEntityId:{}, "
                        + "sourceVersion:{}, relationCount:{}",
                namespace, sourceEntityType, sourceEntityId, sourceVersion, relations.size());
        return relations;
    }

    /**
     * 一次读取一页源实体的指定版本关系，精确匹配每个 ID/version 对，不混入其他版本。
     * 空页不访问数据库；业务快照的解释仍由上层关系 Service 负责。
     */
    public List<EntityRelationDO> listBySourceVersions(String namespace, String sourceEntityType,
            Map<String, Integer> sourceVersions, String relationType) {
        if (sourceVersions == null || sourceVersions.isEmpty()) {
            return Collections.emptyList();
        }
        if (sourceVersions.size() > SOURCE_BATCH_LIMIT || StringUtils.isBlank(relationType)
                || sourceVersions.values().stream().anyMatch(version -> version == null)) {
            throw new IllegalArgumentException(ERROR_SOURCE_BATCH_INVALID);
        }
        sourceVersions.forEach((sourceId, version) ->
                validateSourceIdentity(namespace, sourceEntityType, sourceId, version));
        LambdaQueryWrapper<EntityRelationDO> wrapper = new LambdaQueryWrapper<EntityRelationDO>()
                .eq(EntityRelationDO::getNamespace, namespace)
                .eq(EntityRelationDO::getSourceEntityType, sourceEntityType)
                .eq(EntityRelationDO::getRelationType, relationType);
        wrapper.and(query -> sourceVersions.forEach((sourceId, version) -> query.or(pair ->
                pair.eq(EntityRelationDO::getSourceEntityId, sourceId)
                        .eq(EntityRelationDO::getSourceVersion, version))));
        wrapper.orderByAsc(EntityRelationDO::getSourceEntityId)
                .orderByAsc(EntityRelationDO::getSortNo).orderByAsc(EntityRelationDO::getId);
        List<EntityRelationDO> relations = entityRelationMapper.selectList(wrapper).stream()
                .map(this::copyRelation).collect(Collectors.toList());
        log.info("SkillFactory批量查询版本实体关系完成, namespace:{}, sourceEntityType:{}, "
                        + "relationType:{}, sourceCount:{}, relationCount:{}",
                namespace, sourceEntityType, relationType, sourceVersions.size(), relations.size());
        return relations;
    }

    /**
     * 完整覆盖指定源版本的关系集合。
     *
     * <p>空集合会删除该源版本的所有关系；同一数据源事务中先删后插，避免能力和组件只落一半。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public List<EntityRelationDO> replaceBySourceVersion(String namespace, String sourceEntityType,
            String sourceEntityId, int sourceVersion, List<EntityRelationDO> relations, String operator) {
        validateSourceIdentity(namespace, sourceEntityType, sourceEntityId, sourceVersion);
        List<EntityRelationDO> normalized = normalizeRelations(namespace, sourceEntityType, sourceEntityId,
                sourceVersion, relations, operator, false);
        List<EntityRelationDO> saved =
                replaceBySourceVersionDb(namespace, sourceEntityType, sourceEntityId, sourceVersion, normalized);
        log.info("SkillFactory完整覆盖实体关系完成, namespace:{}, sourceEntityType:{}, sourceEntityId:{}, "
                        + "sourceVersion:{}, relationCount:{}, operator:{}",
                namespace, sourceEntityType, sourceEntityId, sourceVersion, saved.size(), operator);
        return saved;
    }

    /**
     * 把一个源版本的完整关系集合复制到新版本。
     *
     * <p>目标版本原有关系会被完整覆盖；源版本保持不变。用于 `CHANGE_CREATE` 继承所选正式版本的
     * 能力和组件关系，而不是创建独立关系版本头。
     */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public List<EntityRelationDO> copySourceVersion(String namespace, String sourceEntityType,
            String sourceEntityId, int baseSourceVersion, int targetSourceVersion, String operator) {
        validateSourceIdentity(namespace, sourceEntityType, sourceEntityId, baseSourceVersion);
        validateSourceIdentity(namespace, sourceEntityType, sourceEntityId, targetSourceVersion);
        if (baseSourceVersion == targetSourceVersion) {
            return listBySourceVersion(namespace, sourceEntityType, sourceEntityId, baseSourceVersion);
        }
        List<EntityRelationDO> sourceRelations =
                listBySourceVersionDb(namespace, sourceEntityType, sourceEntityId, baseSourceVersion);
        List<EntityRelationDO> targetRelations = normalizeRelations(namespace, sourceEntityType, sourceEntityId,
                targetSourceVersion, sourceRelations, operator, true);
        List<EntityRelationDO> saved = replaceBySourceVersionDb(
                namespace, sourceEntityType, sourceEntityId, targetSourceVersion, targetRelations);
        log.info("SkillFactory复制实体关系版本完成, namespace:{}, sourceEntityType:{}, sourceEntityId:{}, "
                        + "baseVersion:{}, targetVersion:{}, relationCount:{}, operator:{}",
                namespace, sourceEntityType, sourceEntityId, baseSourceVersion, targetSourceVersion,
                saved.size(), operator);
        return saved;
    }

    private List<EntityRelationDO> listBySourceVersionDb(String namespace, String sourceEntityType,
            String sourceEntityId, int sourceVersion) {
        LambdaQueryWrapper<EntityRelationDO> wrapper = sourceVersionWrapper(
                namespace, sourceEntityType, sourceEntityId, sourceVersion);
        wrapper.orderByAsc(EntityRelationDO::getSortNo).orderByAsc(EntityRelationDO::getId);
        return entityRelationMapper.selectList(wrapper).stream()
                .map(this::copyRelation)
                .collect(Collectors.toList());
    }

    private List<EntityRelationDO> replaceBySourceVersionDb(String namespace, String sourceEntityType,
            String sourceEntityId, int sourceVersion, List<EntityRelationDO> relations) {
        entityRelationMapper.delete(sourceVersionWrapper(namespace, sourceEntityType, sourceEntityId, sourceVersion));
        for (EntityRelationDO relation : relations) {
            if (entityRelationMapper.insert(relation) <= 0) {
                log.warn("SkillFactory实体关系DB插入失败, sourceEntityType:{}, sourceEntityId:{}, "
                                + "sourceVersion:{}, relationType:{}, targetEntityId:{}",
                        sourceEntityType, sourceEntityId, sourceVersion, relation.getRelationType(),
                        relation.getTargetEntityId());
                throw new IllegalStateException(ERROR_REPLACE_FAILED);
            }
        }
        return relations.stream().map(this::copyRelation).collect(Collectors.toList());
    }

    private List<EntityRelationDO> normalizeRelations(String namespace, String sourceEntityType,
            String sourceEntityId, int sourceVersion, List<EntityRelationDO> relations,
            String operator, boolean resetCreateTime) {
        List<EntityRelationDO> source = relations == null ? Collections.emptyList() : relations;
        long now = System.currentTimeMillis();
        List<EntityRelationDO> result = new ArrayList<>(source.size());
        for (int index = 0; index < source.size(); index++) {
            EntityRelationDO relation = copyRelation(source.get(index));
            validateTarget(relation);
            relation.setId(null)
                    .setNamespace(namespace)
                    .setSourceEntityType(sourceEntityType)
                    .setSourceEntityId(sourceEntityId)
                    .setSourceVersion(sourceVersion)
                    .setSortNo(index)
                    .setSnapshotJson(SkillFactoryJsonColumnSupport.required(
                            relation.getSnapshotJson(), "snapshotJson"))
                    .setAttribute(SkillFactoryJsonColumnSupport.required(
                            StringUtils.defaultIfBlank(relation.getAttribute(), EMPTY_JSON_OBJECT), "attribute"))
                    .setOperator(StringUtils.defaultString(operator))
                    .setUpdateTime(now);
            if (resetCreateTime || relation.getCreateTime() == null) {
                relation.setCreateTime(now);
            }
            result.add(relation);
        }
        return result;
    }

    private void validateSourceIdentity(String namespace, String sourceEntityType,
            String sourceEntityId, int sourceVersion) {
        if (StringUtils.isAnyBlank(namespace, sourceEntityType, sourceEntityId)
                || !sourceEntityId.matches(SAFE_ID_PATTERN)) {
            throw new IllegalArgumentException(ERROR_SOURCE_IDENTITY_INVALID);
        }
        if (sourceVersion <= 0) {
            throw new IllegalArgumentException(ERROR_SOURCE_VERSION_INVALID);
        }
    }

    private void validateTarget(EntityRelationDO relation) {
        if (relation == null || StringUtils.isAnyBlank(relation.getRelationType(),
                relation.getTargetEntityType(), relation.getTargetEntityId(), relation.getTargetEntityCode())) {
            throw new IllegalArgumentException(ERROR_TARGET_INVALID);
        }
    }

    private LambdaQueryWrapper<EntityRelationDO> sourceVersionWrapper(String namespace,
            String sourceEntityType, String sourceEntityId, int sourceVersion) {
        LambdaQueryWrapper<EntityRelationDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(EntityRelationDO::getNamespace, namespace)
                .eq(EntityRelationDO::getSourceEntityType, sourceEntityType)
                .eq(EntityRelationDO::getSourceEntityId, sourceEntityId)
                .eq(EntityRelationDO::getSourceVersion, sourceVersion);
        return wrapper;
    }

    private EntityRelationDO copyRelation(EntityRelationDO source) {
        if (source == null) {
            return new EntityRelationDO();
        }
        return new EntityRelationDO()
                .setId(source.getId())
                .setNamespace(source.getNamespace())
                .setSourceEntityType(source.getSourceEntityType())
                .setSourceEntityId(source.getSourceEntityId())
                .setSourceVersion(source.getSourceVersion())
                .setRelationType(source.getRelationType())
                .setTargetEntityType(source.getTargetEntityType())
                .setTargetEntityId(source.getTargetEntityId())
                .setTargetEntityCode(source.getTargetEntityCode())
                .setTargetVersion(source.getTargetVersion())
                .setRelationMode(source.getRelationMode())
                .setSnapshotJson(source.getSnapshotJson())
                .setSortNo(source.getSortNo() == null ? INITIAL_SORT_NO : source.getSortNo())
                .setAttribute(source.getAttribute())
                .setOperator(source.getOperator())
                .setCreateTime(source.getCreateTime())
                .setUpdateTime(source.getUpdateTime());
    }

}
