package dev.a2flow.management.storage.db.repository;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.storage.db.entity.CapabilityActionDraftDO;
import dev.a2flow.management.storage.db.mapper.CapabilityActionDraftMapper;

import lombok.extern.slf4j.Slf4j;

/**
 * 能力中心草稿 Repository。
 *
 * <p>该 Repository 是 CapabilityAction 注册/编辑页的唯一存储边界：它只读写
 * `skill_capability_action_draft` 正式表，并负责 DO 与 canonical draft DTO 的转换。上游 Service
 * 负责字段语义、校验和发布门禁；本类不调用 API、不生成 Tool，也不处理浏览器 curl 凭证。
 */
@Repository
@Slf4j
public class CapabilityActionDraftRepository {

    private static final int NOT_DELETED = 0;
    private static final int INITIAL_REVISION = 1;
    private static final String STATUS_DRAFT = "DRAFT";
    private static final String FIELD_BASIC_INFO = "basicInfo";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_NAME_CN = "nameCn";
    private static final String FIELD_TECHNICAL_OWNER = "technicalOwner";
    private static final String FIELD_SUPPORTED_CLIENTS = "supportedClients";
    private static final String FIELD_CLIENT_VARIANTS = "clientVariants";
    private static final String FIELD_API_SOURCE = "apiSource";
    private static final String FIELD_SOURCE_TYPE = "sourceType";
    private static final String FIELD_GOVERNANCE = "governance";
    private static final String FIELD_SIDE_EFFECT_LEVEL = "sideEffectLevel";
    private static final String FIELD_APPROVAL_POLICY = "approvalPolicy";
    private static final String SOURCE_TYPE_MIXED = "MIXED";
    private static final String ERROR_DRAFT_NOT_FOUND = "capability draft not found";
    private static final String ERROR_REVISION_CONFLICT = "capability draft revision conflict";

    @Resource
    private CapabilityActionDraftMapper capabilityActionDraftMapper;

    /**
     * 新建能力草稿。
     */
    public CapabilityActionDraft insert(CapabilityActionDraft draft) {
        return insertDb(draft);
    }

    /**
     * 查询单个能力草稿。
     */
    public CapabilityActionDraft find(String draftId) {
        return findDb(draftId);
    }

    /**
     * 查询能力草稿列表。
     */
    public List<CapabilityActionDraft> list(String keyword) {
        return listDb(keyword);
    }

    /**
     * 按 expectedRevision 原子更新完整 canonical draft。
     */
    public CapabilityActionDraft update(CapabilityActionDraft draft, int expectedRevision) {
        return updateDb(draft, expectedRevision);
    }

    private CapabilityActionDraft insertDb(CapabilityActionDraft draft) {
        CapabilityActionDraftDO draftDO = toDO(draft);
        long now = System.currentTimeMillis();
        String modifier = StringUtils.defaultString(draftDO.getModifier());
        draftDO.setRevision(INITIAL_REVISION)
                .setStatus(STATUS_DRAFT)
                .setCreator(StringUtils.defaultIfBlank(draftDO.getCreator(), modifier))
                .setModifier(modifier)
                .setDeleted(NOT_DELETED)
                .setCreateTime(now)
                .setUpdateTime(now);
        int rows = capabilityActionDraftMapper.insert(draftDO);
        if (rows <= 0) {
            throw new IllegalStateException("insert capability draft failed");
        }
        log.info("能力中心草稿已写入DB, draftId:{}, actionCode:{}, modifier:{}",
                draftDO.getDraftId(), draftDO.getActionCode(), draftDO.getModifier());
        return toDraft(draftDO);
    }

    private CapabilityActionDraft findDb(String draftId) {
        CapabilityActionDraftDO draftDO = capabilityActionDraftMapper.selectOne(new LambdaQueryWrapper<CapabilityActionDraftDO>()
                .eq(CapabilityActionDraftDO::getDraftId, draftId)
                .eq(CapabilityActionDraftDO::getDeleted, NOT_DELETED)
                .last("LIMIT 1"));
        if (draftDO == null) {
            log.info("能力中心草稿DB未命中, draftId:{}", draftId);
            return null;
        }
        log.info("能力中心草稿DB命中, draftId:{}, revision:{}", draftId, draftDO.getRevision());
        return toDraft(draftDO);
    }

    private List<CapabilityActionDraft> listDb(String keyword) {
        List<CapabilityActionDraftDO> records = capabilityActionDraftMapper.selectList(
                new LambdaQueryWrapper<CapabilityActionDraftDO>()
                        .eq(CapabilityActionDraftDO::getDeleted, NOT_DELETED)
                        .orderByDesc(CapabilityActionDraftDO::getUpdateTime));
        return records.stream()
                .filter(draftDO -> matchesKeyword(draftDO, keyword))
                .map(this::toDraft)
                .collect(Collectors.toList());
    }

    private CapabilityActionDraft updateDb(CapabilityActionDraft draft, int expectedRevision) {
        CapabilityActionDraftDO current = findDOByDraftId(draft.getDraftId());
        if (current == null) {
            throw new IllegalArgumentException(ERROR_DRAFT_NOT_FOUND);
        }
        CapabilityActionDraftDO updated = toDO(draft)
                .setId(current.getId())
                .setRevision(expectedRevision + 1)
                .setStatus(StringUtils.defaultIfBlank(draft.getStatus(), current.getStatus()))
                .setCreator(current.getCreator())
                .setModifier(StringUtils.defaultIfBlank(draft.getModifier(), current.getModifier()))
                .setDeleted(NOT_DELETED)
                .setCreateTime(current.getCreateTime())
                .setUpdateTime(System.currentTimeMillis());
        int rows = capabilityActionDraftMapper.update(updated, new LambdaUpdateWrapper<CapabilityActionDraftDO>()
                .eq(CapabilityActionDraftDO::getId, current.getId())
                .eq(CapabilityActionDraftDO::getRevision, expectedRevision)
                .eq(CapabilityActionDraftDO::getDeleted, NOT_DELETED));
        if (rows <= 0) {
            throw new IllegalStateException(ERROR_REVISION_CONFLICT);
        }
        log.info("能力中心草稿DB更新完成, draftId:{}, revision:{}->{}, modifier:{}",
                updated.getDraftId(), expectedRevision, updated.getRevision(), updated.getModifier());
        return toDraft(updated);
    }

    private CapabilityActionDraftDO findDOByDraftId(String draftId) {
        return capabilityActionDraftMapper.selectOne(new LambdaQueryWrapper<CapabilityActionDraftDO>()
                .eq(CapabilityActionDraftDO::getDraftId, draftId)
                .eq(CapabilityActionDraftDO::getDeleted, NOT_DELETED)
                .last("LIMIT 1"));
    }

    private boolean matchesKeyword(CapabilityActionDraftDO draftDO, String keyword) {
        if (StringUtils.isBlank(keyword)) {
            return true;
        }
        String lowerKeyword = keyword.toLowerCase(Locale.ROOT);
        return containsIgnoreCase(draftDO.getDraftId(), lowerKeyword)
                || containsIgnoreCase(draftDO.getActionCode(), lowerKeyword)
                || containsIgnoreCase(draftDO.getNameCn(), lowerKeyword);
    }

    private boolean containsIgnoreCase(String value, String lowerKeyword) {
        return StringUtils.contains(StringUtils.lowerCase(value), lowerKeyword);
    }

    private CapabilityActionDraftDO toDO(CapabilityActionDraft draft) {
        Map<String, Object> canonicalDraft = draft.getDraft() == null
                ? Collections.emptyMap() : draft.getDraft();
        Map<String, Object> basicInfo = mapValue(canonicalDraft.get(FIELD_BASIC_INFO));
        Map<String, Object> governance = mapValue(canonicalDraft.get(FIELD_GOVERNANCE));
        return new CapabilityActionDraftDO()
                .setDraftId(draft.getDraftId())
                .setActionCode(StringUtils.trimToNull(stringValue(basicInfo.get(FIELD_ACTION_CODE))))
                .setNameCn(stringValue(basicInfo.get(FIELD_NAME_CN)))
                .setBusinessDomain(StringUtils.EMPTY)
                .setTechnicalOwner(stringValue(basicInfo.get(FIELD_TECHNICAL_OWNER)))
                .setSourceType(projectSourceType(canonicalDraft))
                .setSideEffectLevel(stringValue(governance.get(FIELD_SIDE_EFFECT_LEVEL)))
                .setApprovalPolicy(stringValue(governance.get(FIELD_APPROVAL_POLICY)))
                .setStatus(draft.getStatus())
                .setRevision(draft.getRevision())
                .setDraftJson(JsonSupport.toJSON(canonicalDraft))
                .setValidationJson(JsonSupport.toJSON(validationMap(draft)))
                .setCreator(draft.getCreator())
                .setModifier(draft.getModifier());
    }

    /**
     * 从端契约派生列表检索列；draftJson/clientVariants 仍是唯一技术契约事实源。
     *
     * <p>所有支持端来源一致时保留来源类型，不一致时投影为 MIXED。该方法不读取旧根级来源，
     * 也不为缺失端契约制造兼容值。
     */
    private String projectSourceType(Map<String, Object> canonicalDraft) {
        Map<String, Object> variants = mapValue(canonicalDraft.get(FIELD_CLIENT_VARIANTS));
        Set<String> sourceTypes = new LinkedHashSet<>();
        for (String client : stringList(canonicalDraft.get(FIELD_SUPPORTED_CLIENTS))) {
            String sourceType = stringValue(mapValue(mapValue(variants.get(client))
                    .get(FIELD_API_SOURCE)).get(FIELD_SOURCE_TYPE));
            if (StringUtils.isNotBlank(sourceType)) {
                sourceTypes.add(sourceType);
            }
        }
        if (sourceTypes.size() == 1) {
            return sourceTypes.iterator().next();
        }
        return sourceTypes.size() > 1 ? SOURCE_TYPE_MIXED : StringUtils.EMPTY;
    }

    private CapabilityActionDraft toDraft(CapabilityActionDraftDO draftDO) {
        Map<String, Object> draft = parseMap(draftDO.getDraftJson());
        Map<String, Object> validation = parseMap(draftDO.getValidationJson());
        return new CapabilityActionDraft()
                .setDraftId(draftDO.getDraftId())
                .setRevision(draftDO.getRevision())
                .setStatus(draftDO.getStatus())
                .setDraft(draft)
                .setValidationErrors(stringList(validation.get("errors")))
                .setValidationWarnings(stringList(validation.get("warnings")))
                .setValidationStatus(stringValue(validation.get("status")))
                .setCreator(draftDO.getCreator())
                .setModifier(draftDO.getModifier())
                .setCreateTime(draftDO.getCreateTime())
                .setUpdateTime(draftDO.getUpdateTime());
    }

    private Map<String, Object> validationMap(CapabilityActionDraft draft) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("errors", draft.getValidationErrors());
        result.put("warnings", draft.getValidationWarnings());
        result.put("status", draft.getValidationStatus());
        return result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseMap(String json) {
        if (StringUtils.isBlank(json)) {
            return new LinkedHashMap<>();
        }
        Map<String, Object> parsed = JsonSupport.fromJSON(json, Map.class);
        return parsed == null ? new LinkedHashMap<>() : parsed;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        if (!(value instanceof Map)) {
            return Collections.emptyMap();
        }
        return (Map<String, Object>) value;
    }

    private List<String> stringList(Object value) {
        if (!(value instanceof List)) {
            return new ArrayList<>();
        }
        return ((List<?>) value).stream().map(String::valueOf).collect(Collectors.toList());
    }

    private String stringValue(Object value) {
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }

}
