package dev.a2flow.management.lifecycle;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.model.SkillFactoryEntityRelationConstants;
import dev.a2flow.management.storage.db.entity.EntityRelationDO;
import dev.a2flow.management.storage.db.repository.EntityRelationRepository;

import lombok.Data;
import lombok.experimental.Accessors;
import lombok.extern.slf4j.Slf4j;

/**
 * 业务能力分类关系领域服务。
 *
 * <p>业务域、能力域和所属专员只以当前草稿 revision 对应的 `entity_relation` 为事实源。本服务负责
 * 受控配置解析、分类关系覆盖和版本继承；不读取 legacy 草稿 JSON 或历史业务域列，也不做兼容回退。
 */
@Service
@Slf4j
public class CapabilityActionClassificationRelationService {

    private static final String FIELD_ID = "id";
    private static final String FIELD_NAME = "name";
    private static final String FIELD_VALUE = "value";
    private static final String FIELD_LABEL = "label";
    private static final String FIELD_BUSINESS_DOMAIN = "businessDomain";
    private static final String FIELD_BUSINESS_DOMAIN_NAME = "businessDomainName";
    private static final String FIELD_CAPABILITY_DOMAIN = "capabilityDomain";
    private static final String FIELD_CAPABILITY_DOMAIN_NAME = "capabilityDomainName";
    private static final String FIELD_SPECIALIST_ID = "specialistId";
    private static final String FIELD_SPECIALIST_NAME = "specialistName";
    private static final String EMPTY_JSON_OBJECT = "{}";
    private static final String ERROR_SPECIALIST_REQUIRED = "所属专员不能为空";
    private static final String ERROR_SELECTION_INVALID = "业务能力分类选择不完整";
    private static final String ERROR_CREATE_SELECTION_PARTIAL =
            "业务能力分类选择必须全部为空或全部填写";
    private static final String ERROR_SNAPSHOT_INVALID = "业务能力分类关系快照格式不合法";
    private static final Set<String> CLASSIFICATION_RELATION_TYPES = Set.of(
            SkillFactoryEntityRelationConstants.RELATION_TYPE_CAPABILITY_BELONGS_TO_BUSINESS_DOMAIN,
            SkillFactoryEntityRelationConstants.RELATION_TYPE_CAPABILITY_BELONGS_TO_CAPABILITY_DOMAIN,
            SkillFactoryEntityRelationConstants.RELATION_TYPE_CAPABILITY_BELONGS_TO_SPECIALIST);

    @Resource
    private SkillFactoryPageConfigService pageConfigService;

    @Resource
    private EntityRelationRepository entityRelationRepository;

    /** 解析并校验页面提交的完整受控分类选择。 */
    public ClassificationSelection resolveSelection(String businessDomain, String capabilityDomain,
            String specialistIds) {
        List<Map<String, Object>> specialists = pageConfigService.resolveSpecialists(specialistIds);
        if (specialists.isEmpty()) {
            throw new IllegalArgumentException(ERROR_SPECIALIST_REQUIRED);
        }
        return new ClassificationSelection()
                .setBusinessDomain(pageConfigService.resolveBusinessDomain(businessDomain))
                .setCapabilityDomain(pageConfigService.resolveCapabilityDomain(capabilityDomain))
                .setSpecialists(specialists);
    }

    /**
     * 解析创建阶段分类参数：首次中文名注册允许三项全部缺省，其他创建请求必须一次提交完整选择。
     */
    public Optional<ClassificationSelection> resolveCreateSelection(
            String businessDomain, String capabilityDomain, String specialistIds) {
        boolean hasBusinessDomain = StringUtils.isNotBlank(businessDomain);
        boolean hasCapabilityDomain = StringUtils.isNotBlank(capabilityDomain);
        boolean hasSpecialists = StringUtils.isNotBlank(specialistIds);
        if (!hasBusinessDomain && !hasCapabilityDomain && !hasSpecialists) {
            return Optional.empty();
        }
        if (!hasBusinessDomain || !hasCapabilityDomain || !hasSpecialists) {
            throw new IllegalArgumentException(ERROR_CREATE_SELECTION_PARTIAL);
        }
        return Optional.of(resolveSelection(businessDomain, capabilityDomain, specialistIds));
    }

    /** 覆盖指定 revision 的三类分类关系，并保留同 revision 的其他关系。 */
    public void replaceForRevision(String draftId, int revision, ClassificationSelection selection,
            String operator) {
        List<EntityRelationDO> relations = entityRelationRepository.listBySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_CAPABILITY_ACTION, draftId, revision);
        replace(draftId, revision, relations, selection, operator);
    }

    /** 从基线 revision 继承全部关系，仅用新选择替换三类分类关系。 */
    public void copyAndReplaceForRevision(String draftId, int baseRevision, int targetRevision,
            ClassificationSelection selection, String operator) {
        List<EntityRelationDO> relations = entityRelationRepository.listBySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_CAPABILITY_ACTION, draftId, baseRevision);
        replace(draftId, targetRevision, relations, selection, operator);
    }

    /** 读取指定草稿 revision 的完整有序关系，供管理投影与发布冻结复用。 */
    public List<EntityRelationDO> listForRevision(String draftId, int revision) {
        if (StringUtils.isBlank(draftId) || revision <= 0) {
            return Collections.emptyList();
        }
        return entityRelationRepository.listBySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_CAPABILITY_ACTION, draftId, revision);
    }

    /** 完整复制关系版本，供不改变分类的校验型 revision 递增使用。 */
    public void copyForRevision(String draftId, int baseRevision, int targetRevision, String operator) {
        entityRelationRepository.copySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_CAPABILITY_ACTION,
                draftId, baseRevision, targetRevision, operator);
    }

    /** 把当前 relation 事实投影为管理接口的 transient 字段。 */
    public CapabilityActionDraft project(CapabilityActionDraft draft) {
        if (draft == null || StringUtils.isBlank(draft.getDraftId()) || draft.getRevision() == null) {
            return draft;
        }
        List<String> specialistIds = new ArrayList<>();
        List<String> specialistNames = new ArrayList<>();
        for (EntityRelationDO relation : listForRevision(draft.getDraftId(), draft.getRevision())) {
            if (StringUtils.equals(relation.getRelationType(),
                    SkillFactoryEntityRelationConstants.RELATION_TYPE_CAPABILITY_BELONGS_TO_BUSINESS_DOMAIN)) {
                Map<String, Object> snapshot = parseSnapshot(relation);
                draft.setBusinessDomain(relation.getTargetEntityId());
                draft.setBusinessDomainName(requiredSnapshotString(snapshot, FIELD_BUSINESS_DOMAIN_NAME));
            } else if (StringUtils.equals(relation.getRelationType(),
                    SkillFactoryEntityRelationConstants.RELATION_TYPE_CAPABILITY_BELONGS_TO_CAPABILITY_DOMAIN)) {
                Map<String, Object> snapshot = parseSnapshot(relation);
                draft.setCapabilityDomain(relation.getTargetEntityId());
                draft.setCapabilityDomainName(requiredSnapshotString(snapshot, FIELD_CAPABILITY_DOMAIN_NAME));
            } else if (StringUtils.equals(relation.getRelationType(),
                    SkillFactoryEntityRelationConstants.RELATION_TYPE_CAPABILITY_BELONGS_TO_SPECIALIST)) {
                Map<String, Object> snapshot = parseSnapshot(relation);
                specialistIds.add(relation.getTargetEntityId());
                specialistNames.add(requiredSnapshotString(snapshot, FIELD_SPECIALIST_NAME));
            }
        }
        draft.setSpecialistId(String.join(",", specialistIds));
        draft.setSpecialistName(String.join(",", specialistNames));
        return draft;
    }

    /** 按 relation 稳定 ID 执行业务域、能力域和专员筛选，三类条件使用 AND 语义。 */
    public boolean matches(CapabilityActionDraft draft, String businessDomain,
            String capabilityDomain, String specialistId) {
        if (draft == null) {
            return false;
        }
        CapabilityActionDraft projected = StringUtils.isNotBlank(draft.getBusinessDomain())
                ? draft : project(draft);
        String expectedBusinessDomain = StringUtils.trimToEmpty(businessDomain);
        String expectedCapabilityDomain = StringUtils.trimToEmpty(capabilityDomain);
        String expectedSpecialistId = StringUtils.trimToEmpty(specialistId);
        boolean businessMatches = StringUtils.isBlank(expectedBusinessDomain)
                || StringUtils.equals(expectedBusinessDomain, projected.getBusinessDomain());
        boolean capabilityMatches = StringUtils.isBlank(expectedCapabilityDomain)
                || StringUtils.equals(expectedCapabilityDomain, projected.getCapabilityDomain());
        String specialistIds = "," + StringUtils.defaultString(projected.getSpecialistId()) + ",";
        boolean specialistMatches = StringUtils.isBlank(expectedSpecialistId)
                || StringUtils.contains(specialistIds, "," + expectedSpecialistId + ",");
        return businessMatches && capabilityMatches && specialistMatches;
    }

    private void replace(String draftId, int revision, List<EntityRelationDO> sourceRelations,
            ClassificationSelection selection, String operator) {
        requireSelection(selection);
        List<EntityRelationDO> targetRelations = new ArrayList<>();
        if (sourceRelations != null) {
            for (EntityRelationDO relation : sourceRelations) {
                if (relation != null && !CLASSIFICATION_RELATION_TYPES.contains(relation.getRelationType())) {
                    targetRelations.add(relation);
                }
            }
        }
        targetRelations.add(toDomainRelation(selection.getBusinessDomain(),
                SkillFactoryEntityRelationConstants.RELATION_TYPE_CAPABILITY_BELONGS_TO_BUSINESS_DOMAIN,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_BUSINESS_DOMAIN,
                FIELD_BUSINESS_DOMAIN, FIELD_BUSINESS_DOMAIN_NAME));
        targetRelations.add(toDomainRelation(selection.getCapabilityDomain(),
                SkillFactoryEntityRelationConstants.RELATION_TYPE_CAPABILITY_BELONGS_TO_CAPABILITY_DOMAIN,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_CAPABILITY_DOMAIN,
                FIELD_CAPABILITY_DOMAIN, FIELD_CAPABILITY_DOMAIN_NAME));
        for (Map<String, Object> specialist : selection.getSpecialists()) {
            targetRelations.add(toSpecialistRelation(specialist));
        }
        entityRelationRepository.replaceBySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_CAPABILITY_ACTION,
                draftId, revision, targetRelations, operator);
        log.info("业务能力分类关系覆盖完成, draftId:{}, revision:{}, specialistCount:{}, operator:{}",
                draftId, revision, selection.getSpecialists().size(), operator);
    }

    private EntityRelationDO toDomainRelation(Map<String, Object> option, String relationType,
            String targetEntityType, String valueField, String nameField) {
        String value = mapString(option, FIELD_VALUE);
        String label = mapString(option, FIELD_LABEL);
        if (StringUtils.isAnyBlank(value, label)) {
            throw new IllegalArgumentException(ERROR_SELECTION_INVALID);
        }
        Map<String, Object> snapshot = new LinkedHashMap<>();
        snapshot.put(valueField, value);
        snapshot.put(nameField, label);
        return relation(relationType, targetEntityType, value, snapshot);
    }

    private EntityRelationDO toSpecialistRelation(Map<String, Object> specialist) {
        String specialistId = mapString(specialist, FIELD_ID);
        String specialistName = mapString(specialist, FIELD_NAME);
        if (StringUtils.isAnyBlank(specialistId, specialistName)) {
            throw new IllegalArgumentException(ERROR_SELECTION_INVALID);
        }
        Map<String, Object> snapshot = new LinkedHashMap<>();
        snapshot.put(FIELD_SPECIALIST_ID, specialistId);
        snapshot.put(FIELD_SPECIALIST_NAME, specialistName);
        return relation(SkillFactoryEntityRelationConstants.RELATION_TYPE_CAPABILITY_BELONGS_TO_SPECIALIST,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_SPECIALIST, specialistId, snapshot);
    }

    private EntityRelationDO relation(String relationType, String targetEntityType, String targetId,
            Map<String, Object> snapshot) {
        return new EntityRelationDO()
                .setRelationType(relationType)
                .setTargetEntityType(targetEntityType)
                .setTargetEntityId(targetId)
                .setTargetEntityCode(targetId)
                .setTargetVersion(StringUtils.EMPTY)
                .setRelationMode(SkillFactoryEntityRelationConstants.RELATION_MODE_ASSIGNED)
                .setSnapshotJson(JsonSupport.toJSON(snapshot))
                .setAttribute(EMPTY_JSON_OBJECT);
    }

    private void requireSelection(ClassificationSelection selection) {
        if (selection == null || selection.getBusinessDomain() == null
                || selection.getCapabilityDomain() == null || selection.getSpecialists() == null
                || selection.getSpecialists().isEmpty()) {
            throw new IllegalArgumentException(ERROR_SELECTION_INVALID);
        }
    }

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
                return (Map<String, Object>) parsed;
            }
        } catch (Exception exception) {
            log.warn("业务能力分类关系快照解析失败, relationId:{}, targetEntityId:{}, error:{}",
                    relation.getId(), relation.getTargetEntityId(), exception.getMessage());
            throw new IllegalStateException(ERROR_SNAPSHOT_INVALID, exception);
        }
        log.warn("业务能力分类关系快照不是JSON对象, relationId:{}, targetEntityId:{}",
                relation.getId(), relation.getTargetEntityId());
        throw new IllegalStateException(ERROR_SNAPSHOT_INVALID);
    }

    private String requiredSnapshotString(Map<String, Object> snapshot, String field) {
        String value = mapString(snapshot, field);
        if (StringUtils.isBlank(value)) {
            throw new IllegalStateException(ERROR_SNAPSHOT_INVALID);
        }
        return value;
    }

    /** 页面提交完成受控解析后的分类选择。 */
    @Data
    @Accessors(chain = true)
    public static class ClassificationSelection {
        private Map<String, Object> businessDomain;
        private Map<String, Object> capabilityDomain;
        private List<Map<String, Object>> specialists;
    }
}
