package dev.a2flow.management.a2ui.application;

import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.ACTION_CODE_RESERVED;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.CATALOG_ENVIRONMENT_MISMATCH;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.CATALOG_SUPPORT_MISSING;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.DRAFT_INVALID;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.PROTOCOL_UNSUPPORTED;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiActionBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiActionDeclaration;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationBuild;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationCatalogRef;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationDraft;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCurrentCapabilityContract;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiLoadBinding;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogModels.A2uiCatalogComponentContract;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogFunctionContractValidator;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogSourceType;
import dev.a2flow.management.a2ui.registry.A2uiComponentOriginType;
import dev.a2flow.management.release.PublishedAssetQueryService;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.PublishedAssetSnapshot;

import lombok.extern.slf4j.Slf4j;

/**
 * A2UI Application 作者态 source 到发布 manifest 的服务端编译入口。
 *
 * <p>上游是共享 A2UI_APPLICATION release adapter；本服务补齐客户端无权提交的 v0.9.1 协议快照、
 * 指定发布环境的精确 Catalog，再解析当前生效 CapabilityAction 完成 schema
 * 兼容校验。成功分支在反序列化前保留严格类型边界，下游只得到 immutable Application Build JSON。本服务不读取运行态消息、
 * 不执行 Action、
 * 不调用 Adviser/agent-service，也不在 Catalog/Capability 缺失时回退到其他环境或 Registry 当前值。
 */
@Service
@Slf4j
public class A2uiApplicationManifestCompilerService {

    private static final String PROTOCOL_VERSION = "v0.9.1";
    private static final String PROTOCOL_STATUS = "CURRENT_PRODUCTION";
    private static final String PROTOCOL_SOURCE_COMMIT = "420c6183c400e4b84fe3f9e084906725062a6d56";
    private static final String FIELD_CATALOG_ID = "catalogId";
    private static final String FIELD_CATALOG_SOURCE_TYPE = "catalogSourceType";
    private static final String FIELD_COMPONENT_ORIGIN_TYPE = "componentOriginType";
    private static final String FIELD_CLIENT_DATA_MODEL = "clientDataModel";
    private static final String FIELD_PROTOCOL_VERSION = "protocolVersion";
    private static final String FIELD_COMPONENTS = "components";
    private static final String FIELD_CONTRACT = "contract";
    private static final String FIELD_COMPONENT_CODE = "componentCode";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_NAME_CN = "nameCn";
    private static final String BUILD_ID_PREFIX = "a2ui_build_";
    private static final Map<String, String> PROTOCOL_SCHEMA_DIGESTS = protocolSchemaDigests();

    @Resource
    private PublishedAssetQueryService publishedAssetQueryService;

    @Resource
    private A2uiCurrentCapabilityResolver currentCapabilityResolver;

    private final A2uiApplicationBuildCompiler compiler;
    private final A2uiCatalogFunctionContractValidator functionContractValidator =
            new A2uiCatalogFunctionContractValidator();
    private final A2uiShowTemplateAnalyzer showTemplateAnalyzer = new A2uiShowTemplateAnalyzer();

    public A2uiApplicationManifestCompilerService() {
        this.compiler = new A2uiApplicationBuildCompiler(A2uiApplicationManifestCompilerService::buildId);
    }

    A2uiApplicationManifestCompilerService(PublishedAssetQueryService publishedAssetQueryService,
            A2uiCurrentCapabilityResolver currentCapabilityResolver,
            A2uiApplicationBuildCompiler compiler) {
        this.publishedAssetQueryService = publishedAssetQueryService;
        this.currentCapabilityResolver = currentCapabilityResolver;
        this.compiler = compiler;
    }

    /**
     * 编译服务端权威 manifest；assetKey/source appCode 与目标环境 Catalog 必须精确一致。
     */
    public A2uiApplicationBuild compile(
            String assetKey, String sourceJson, ReleaseEnvironment environment) {
        if (StringUtils.isAnyBlank(assetKey, sourceJson)
                || publishedAssetQueryService == null
                || currentCapabilityResolver == null || environment == null) {
            throw failure(DRAFT_INVALID);
        }
        A2uiApplicationDraft draft = parseDraft(sourceJson);
        if (!StringUtils.equals(assetKey, draft.getAppCode())) {
            throw failure(DRAFT_INVALID);
        }
        String catalogId = draft.getCatalogId();
        if (StringUtils.isBlank(catalogId)) {
            throw failure(DRAFT_INVALID);
        }
        PublishedAssetSnapshot publishedCatalog;
        try {
            publishedCatalog = publishedAssetQueryService.requirePublished(
                    ReleaseAssetType.A2UI_CATALOG, catalogId, environment);
        } catch (RuntimeException exception) {
            throw failure(CATALOG_ENVIRONMENT_MISMATCH);
        }
        AssetSnapshot catalogSnapshot = publishedCatalog.getSnapshot();
        String catalogRevision = publishedCatalog.getVersionId();
        if (catalogSnapshot == null || StringUtils.isAnyBlank(
                catalogRevision, catalogSnapshot.getDigest(), catalogSnapshot.getPayloadJson())) {
            throw failure(CATALOG_SUPPORT_MISSING);
        }
        Map<String, Object> catalogPayload = parseMap(catalogSnapshot.getPayloadJson());
        if (!StringUtils.equals(catalogId, text(catalogPayload.get(FIELD_CATALOG_ID)))) {
            throw failure(CATALOG_SUPPORT_MISSING);
        }
        A2uiCatalogSourceType catalogSourceType = catalogSourceType(catalogPayload);
        if (catalogSourceType != A2uiCatalogSourceType.PLATFORM_MANAGED) {
            throw failure(CATALOG_SUPPORT_MISSING);
        }
        if (!StringUtils.equals(PROTOCOL_VERSION, text(catalogPayload.get(FIELD_PROTOCOL_VERSION)))) {
            throw failure(PROTOCOL_UNSUPPORTED);
        }
        List<A2uiCatalogComponentContract> catalogComponents = catalogComponents(
                catalogId, catalogPayload, catalogRevision, catalogSnapshot.getDigest());
        A2uiCatalogFunctionContractValidator.ValidatedFunctionContract functionContract;
        try {
            functionContract = functionContractValidator.publishedContract(
                    catalogId, catalogPayload);
        } catch (RuntimeException exception) {
            throw failure(CATALOG_SUPPORT_MISSING);
        }
        try {
            functionContractValidator.validateMessageTemplateCalls(
                    draft.getShowTemplate().getMessageTemplates(), functionContract);
        } catch (RuntimeException exception) {
            throw failure(DRAFT_INVALID);
        }
        Map<String, A2uiComponentOriginType> componentOrigins = componentOrigins(catalogComponents);
        injectAuthority(draft, catalogId, catalogSourceType, componentOrigins,
                catalogRevision, catalogSnapshot.getDigest());
        validateReservedActionCodes(draft);
        Map<String, A2uiCurrentCapabilityContract> capabilities = currentCapabilityResolver.resolve(
                referencedActionCodes(draft));
        A2uiApplicationBuild build = compiler.compile(
                draft, catalogComponents, capabilities, environment, functionContract);
        log.info("A2UI Application发布manifest编译完成, appCode:{}, environment:{}, appBuildId:{}, "
                        + "capabilityCount:{}",
                assetKey, environment, build.getAppBuildId(), capabilities.size());
        return build;
    }

    /** 校验不可变 Build 固定的 Catalog 已在目标环境精确发布。 */
    public void verifyCatalogPublication(String catalogId, String catalogRevision,
            String catalogDigest, ReleaseEnvironment environment) {
        if (StringUtils.isAnyBlank(catalogId, catalogRevision, catalogDigest)
                || environment == null || publishedAssetQueryService == null) {
            throw failure(CATALOG_ENVIRONMENT_MISMATCH);
        }
        PublishedAssetSnapshot published;
        try {
            published = publishedAssetQueryService.requirePublished(
                    ReleaseAssetType.A2UI_CATALOG, catalogId, environment);
        } catch (RuntimeException exception) {
            throw failure(CATALOG_ENVIRONMENT_MISMATCH);
        }
        AssetSnapshot snapshot = published == null ? null : published.getSnapshot();
        // PRT 固定 Build 身份；晋升后仅接受当前正式版本的同源 Build，摘要仍须精确一致。
        if (snapshot == null
                || (!StringUtils.equals(catalogRevision, published.getVersionId())
                    && !StringUtils.equals(catalogRevision, published.getSourceBuildId()))
                || !StringUtils.equals(catalogDigest, snapshot.getDigest())) {
            throw failure(CATALOG_ENVIRONMENT_MISMATCH);
        }
    }

    private A2uiApplicationDraft parseDraft(String sourceJson) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> source = JsonSupport.fromJSON(sourceJson, Map.class);
            if (source == null || source.containsKey(FIELD_CLIENT_DATA_MODEL)) {
                throw failure(DRAFT_INVALID);
            }
            // 存量 source 同样先校验原始转换形态，禁止反序列化时丢字段或强转字符串。
            A2uiRequestTransformValidator.validate(source);
            A2uiSuccessBranchValidator.validate(source);
            A2uiApplicationDraft draft = JsonSupport.fromJSON(sourceJson, A2uiApplicationDraft.class);
            if (draft == null) {
                throw failure(DRAFT_INVALID);
            }
            return draft;
        } catch (A2uiApplicationValidationException exception) {
            throw exception;
        } catch (Exception exception) {
            throw failure(DRAFT_INVALID);
        }
    }

    private void injectAuthority(A2uiApplicationDraft draft, String catalogId,
            A2uiCatalogSourceType catalogSourceType,
            Map<String, A2uiComponentOriginType> componentOrigins, String catalogRevision,
            String catalogDigest) {
        draft.setProtocolVersion(PROTOCOL_VERSION)
                .setProtocolStatus(PROTOCOL_STATUS)
                .setProtocolSourceCommit(PROTOCOL_SOURCE_COMMIT)
                .setProtocolSchemaDigests(new LinkedHashMap<>(PROTOCOL_SCHEMA_DIGESTS))
                .setCatalog(new A2uiApplicationCatalogRef()
                        .setCatalogId(catalogId)
                        .setRevision(catalogRevision)
                        .setDigest(catalogDigest)
                        .setCatalogSourceType(catalogSourceType)
                        .setComponentOrigins(new LinkedHashMap<>(componentOrigins)));
    }

    private List<A2uiCatalogComponentContract> catalogComponents(String catalogId,
            Map<String, Object> catalogPayload, String catalogRevision, String catalogDigest) {
        Object rawComponents = catalogPayload.get(FIELD_COMPONENTS);
        if (!(rawComponents instanceof List)) {
            throw failure(CATALOG_SUPPORT_MISSING);
        }
        List<A2uiCatalogComponentContract> result = new ArrayList<>();
        for (Object rawComponent : (List<?>) rawComponents) {
            Map<String, Object> component = map(rawComponent);
            Map<String, Object> canonicalContract = new LinkedHashMap<>(map(component.get(FIELD_CONTRACT)));
            canonicalContract.put(FIELD_COMPONENT_CODE, component.get(FIELD_COMPONENT_CODE));
            canonicalContract.put(FIELD_TYPE, component.get(FIELD_TYPE));
            canonicalContract.put(FIELD_NAME_CN, component.get(FIELD_NAME_CN));
            A2uiCatalogComponentContract contract = componentContract(canonicalContract);
            if (contract == null || StringUtils.isBlank(contract.getType())
                    || !isSupportedComponentOrigin(contract.getComponentOriginType())) {
                throw failure(CATALOG_SUPPORT_MISSING);
            }
            contract.setCatalogId(catalogId)
                    .setCatalogRevision(catalogRevision)
                    .setCatalogDigest(catalogDigest);
            result.add(contract);
        }
        return result;
    }

    private A2uiCatalogComponentContract componentContract(Map<String, Object> source) {
        A2uiComponentOriginType originType;
        try {
            originType = A2uiComponentOriginType.parse(
                    text(source.get(FIELD_COMPONENT_ORIGIN_TYPE)));
        } catch (RuntimeException exception) {
            throw failure(CATALOG_SUPPORT_MISSING);
        }
        if (originType == A2uiComponentOriginType.A2UI_OFFICIAL) {
            return new A2uiCatalogComponentContract()
                    .setComponentCode(text(source.get(FIELD_COMPONENT_CODE)))
                    .setType(text(source.get(FIELD_TYPE)))
                    .setNameCn(text(source.get(FIELD_NAME_CN)))
                    .setComponentOriginType(originType);
        }
        return JsonSupport.fromJSON(
                JsonSupport.toJSON(source), A2uiCatalogComponentContract.class);
    }

    private boolean isSupportedComponentOrigin(A2uiComponentOriginType originType) {
        return originType == A2uiComponentOriginType.PLATFORM_CUSTOM
                || originType == A2uiComponentOriginType.A2UI_OFFICIAL;
    }

    private A2uiCatalogSourceType catalogSourceType(Map<String, Object> catalogPayload) {
        try {
            return A2uiCatalogSourceType.parse(text(catalogPayload.get(FIELD_CATALOG_SOURCE_TYPE)));
        } catch (IllegalArgumentException exception) {
            throw failure(CATALOG_SUPPORT_MISSING);
        }
    }

    private Map<String, A2uiComponentOriginType> componentOrigins(
            List<A2uiCatalogComponentContract> components) {
        Map<String, A2uiComponentOriginType> result = new LinkedHashMap<>();
        for (A2uiCatalogComponentContract component : components) {
            if (result.putIfAbsent(component.getType(), component.getComponentOriginType()) != null) {
                throw failure(CATALOG_SUPPORT_MISSING);
            }
        }
        return result;
    }

    private void validateReservedActionCodes(A2uiApplicationDraft draft) {
        for (A2uiActionDeclaration declaration : showTemplateAnalyzer.analyze(
                draft.getShowTemplate(), draft.getCatalog().getCatalogId()).getActionDeclarations()) {
            rejectReservedActionCode(declaration == null ? null : declaration.getActionCode());
        }
        for (A2uiLoadBinding binding : draft.getLoadBindings()) {
            rejectReservedActionCode(binding == null || binding.getCapability() == null
                    ? null : binding.getCapability().getActionCode());
        }
        for (A2uiActionBinding binding : draft.getActionBindings()) {
            rejectReservedActionCode(binding == null ? null : binding.getActionCode());
            rejectReservedActionCode(binding == null || binding.getCapability() == null
                    ? null : binding.getCapability().getActionCode());
        }
    }

    private void rejectReservedActionCode(String actionCode) {
        if (A2uiReservedActionCode.isReserved(actionCode)) {
            throw failure(ACTION_CODE_RESERVED);
        }
    }

    private Set<String> referencedActionCodes(A2uiApplicationDraft draft) {
        Set<String> result = new LinkedHashSet<>();
        for (A2uiLoadBinding binding : draft.getLoadBindings()) {
            if (binding != null && binding.getCapability() != null) {
                result.add(binding.getCapability().getActionCode());
            }
        }
        for (A2uiActionBinding binding : draft.getActionBindings()) {
            if (binding != null && binding.getCapability() != null) {
                result.add(binding.getCapability().getActionCode());
            }
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseMap(String json) {
        try {
            Map<String, Object> result = JsonSupport.fromJSON(json, Map.class);
            return result == null ? Collections.emptyMap() : result;
        } catch (Exception exception) {
            throw failure(CATALOG_SUPPORT_MISSING);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    private String text(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private static String buildId(String sourceDigest) {
        if (StringUtils.isBlank(sourceDigest)) {
            return null;
        }
        return BUILD_ID_PREFIX + StringUtils.removeStart(sourceDigest, "sha256:");
    }

    private static Map<String, String> protocolSchemaDigests() {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("server_to_client.json", "2ba29dbcb57611225c96d3e064d05cf97e9d8224b293c8b20d37b93922a2d30d");
        result.put("client_to_server.json", "f049f8a554296a603cd3c1cef37dd6811006dc90e3ff52ce845d1674cd00a6b7");
        result.put("common_types.json", "ac79788e95e5bdf0a39808953593a53c1bc9fcdcdb55480f4610613c6591e94c");
        result.put("client_capabilities.json", "917ff302b883c8c50475f0fafa836c17620078e7e2089392b322dc5df01de78f");
        result.put("server_capabilities.json", "bdaf275dd2abf279e62637ead1b840744e031d94735ec4f63d0c7c2fe5347dd4");
        result.put("client_data_model.json", "6aefe455be9287caaf2f964ae480e8cf87706718106130908b41df19d5e982be");
        return Collections.unmodifiableMap(result);
    }

    private A2uiApplicationValidationException failure(A2uiApplicationErrorCode errorCode) {
        return new A2uiApplicationValidationException(errorCode);
    }
}
