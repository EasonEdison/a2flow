package dev.a2flow.management.a2ui.registry;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

import dev.a2flow.management.a2ui.catalog.A2uiCatalogErrorCode;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;

import lombok.extern.slf4j.Slf4j;

/**
 * A2UI Atom 管理面投影器。
 *
 * <p>上游是共享 Registry 当前行及服务端发布只读投影，下游是 M 端 Atom 列表与详情。该类允许
 * 缺失 canonical contract 的历史行继续以专用 Registry 身份列展示并被人工修复，同时强制关闭
 * 该行的发布消费状态；它不补造 contract、不读取旧 DSL 字段，也不替代发布域的完整契约校验。
 */
@Slf4j
public final class A2uiAtomAuthoringProjection {

    private static final String FIELD_ID = "id";
    private static final String FIELD_COMPONENT_CODE = "componentCode";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_NAME_CN = "nameCn";
    private static final String FIELD_CATEGORY = "category";
    private static final String FIELD_COMPONENT_ORIGIN_TYPE = "componentOriginType";
    private static final String FIELD_COMPOSITION_KIND = "compositionKind";
    private static final String FIELD_PROPS_SCHEMA = "propsSchema";
    private static final String FIELD_EVENT_SCHEMA = "eventSchema";
    private static final String FIELD_CHILDREN_CONSTRAINT = "childrenConstraint";
    private static final String FIELD_VALID_MESSAGE_EXAMPLE = "validMessageExample";
    private static final String FIELD_INVALID_MESSAGE_EXAMPLE = "invalidMessageExample";
    private static final String FIELD_RELEASE = "release";
    private static final String FIELD_CONTRACT_VALIDATION = "contractValidation";
    private static final String FIELD_VALID = "valid";
    private static final String FIELD_ERROR_CODE = "errorCode";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_ENABLED = "enabled";
    private static final String FIELD_CREATE_TIME = "createTime";
    private static final String FIELD_UPDATE_TIME = "updateTime";

    private A2uiAtomAuthoringProjection() {
    }

    /**
     * 生成 Atom 管理投影；contract 缺失时仅保留专用身份列，并明确返回不可发布的校验事实。
     */
    public static Map<String, Object> project(ComponentAsset asset,
            Map<String, Object> releaseProjection) {
        Map<String, Object> contract = asset == null ? null : asset.getA2uiContract();
        boolean contractValid = contract != null;
        Map<String, Object> source = contractValid ? contract : Collections.emptyMap();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_ID, asset == null ? null : String.valueOf(asset.getId()));
        result.put(FIELD_COMPONENT_CODE, identityValue(contractValid, source,
                FIELD_COMPONENT_CODE, asset == null ? null : asset.getComponentName()));
        result.put(FIELD_TYPE, identityValue(contractValid, source,
                FIELD_TYPE, asset == null ? null : asset.getA2uiComponentType()));
        result.put(FIELD_NAME_CN, identityValue(contractValid, source,
                FIELD_NAME_CN, asset == null ? null : asset.getComponentNameCn()));
        result.put(FIELD_CATEGORY, source.get(FIELD_CATEGORY));
        result.put(FIELD_COMPONENT_ORIGIN_TYPE, source.get(FIELD_COMPONENT_ORIGIN_TYPE));
        if (A2uiComponentOriginType.A2UI_OFFICIAL.name().equals(
                source.get(FIELD_COMPONENT_ORIGIN_TYPE))) {
            result.put("officialCatalogId", source.get("officialCatalogId"));
            result.put("officialSourceCommit", source.get("officialSourceCommit"));
            result.put("officialSchema", source.get("officialSchema"));
        }
        result.put(FIELD_COMPOSITION_KIND, source.get(FIELD_COMPOSITION_KIND));
        result.put(FIELD_PROPS_SCHEMA, source.get(FIELD_PROPS_SCHEMA));
        result.put(FIELD_EVENT_SCHEMA, source.get(FIELD_EVENT_SCHEMA));
        result.put(FIELD_CHILDREN_CONSTRAINT, source.get(FIELD_CHILDREN_CONSTRAINT));
        result.put(FIELD_VALID_MESSAGE_EXAMPLE, source.get(FIELD_VALID_MESSAGE_EXAMPLE));
        result.put(FIELD_INVALID_MESSAGE_EXAMPLE, source.get(FIELD_INVALID_MESSAGE_EXAMPLE));
        result.put(FIELD_RELEASE, failClosedReleaseProjection(releaseProjection, contractValid));
        result.put(FIELD_CONTRACT_VALIDATION, validation(contractValid));
        result.put(FIELD_CREATE_TIME, asset == null ? null : asset.getCreateTime());
        result.put(FIELD_UPDATE_TIME, asset == null ? null : asset.getUpdateTime());
        if (!contractValid) {
            log.warn("A2UI_ATOM管理投影发现canonical contract缺失, id:{}, componentCode:{}",
                    asset == null ? null : asset.getId(),
                    asset == null ? null : asset.getComponentName());
        }
        return result;
    }

    private static Object identityValue(boolean contractValid, Map<String, Object> contract,
            String field, Object repairIdentity) {
        return contractValid ? contract.get(field) : repairIdentity;
    }

    private static Map<String, Object> failClosedReleaseProjection(
            Map<String, Object> projection, boolean contractValid) {
        Map<String, Object> result = copy(projection);
        if (!contractValid) {
            result.put(FIELD_ENABLED, false);
        }
        return result;
    }

    private static Map<String, Object> validation(boolean contractValid) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_VALID, contractValid);
        result.put(FIELD_ERROR_CODE, contractValid ? null
                : A2uiCatalogErrorCode.COMPONENT_CONTRACT_INVALID.getCode());
        result.put(FIELD_MESSAGE, contractValid ? null
                : A2uiCatalogErrorCode.COMPONENT_CONTRACT_INVALID.getMessage());
        return result;
    }

    private static Map<String, Object> copy(Map<String, Object> source) {
        return source == null ? new LinkedHashMap<>() : new LinkedHashMap<>(source);
    }
}
