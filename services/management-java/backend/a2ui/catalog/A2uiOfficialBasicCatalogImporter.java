package dev.a2flow.management.a2ui.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application.A2uiImmutableJsonSupport;
import dev.a2flow.management.a2ui.registry.A2uiComponentOriginType;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.release.ReleaseDigestUtils;

/**
 * 从随服务发布的受控资源构造 v0.9.1 Official Basic Catalog 锁定快照。
 *
 * <p>上游是受信任的 Official 导入用例，下游是共享 Registry 可持久化的 Catalog/atom 当前态。
 * 本类启动时不访问网络，也不直接写数据库；每次导入都重新校验原始文件摘要、Catalog identity、
 * 18 个组件和 14 个函数，任一事实漂移立即失败关闭。普通 M 端写请求不能调用本类伪造 Official 来源。
 */
@Service
public class A2uiOfficialBasicCatalogImporter {

    public static final String CATALOG_ID =
            "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json";
    public static final String SOURCE_COMMIT =
            "420c6183c400e4b84fe3f9e084906725062a6d56";
    public static final String PROTOCOL_VERSION = "v0.9.1";
    public static final String CATALOG_DIGEST =
            "8cc94d0a482e67048f9fc989964ca5da56fe42f531d919315a508989fb22e13e";
    public static final String RULES_DIGEST =
            "ccd5b8158b7d459c26bb92dbe63fcb5d01a78311d39200951c5b062499b854df";

    private static final String DIGEST_PREFIX = "sha256:";
    private static final String RESOURCE_ROOT = "skillfactory/a2ui/v0_9_1/official/";
    private static final String CATALOG_RESOURCE = RESOURCE_ROOT + "basic/catalog.json";
    private static final String RULES_RESOURCE = RESOURCE_ROOT + "basic/rules.txt";
    private static final String ASSET_TYPE_CATALOG = "A2UI_CATALOG";
    private static final String ASSET_TYPE_ATOM = "A2UI_ATOM";
    private static final String ERROR_RESOURCE_INVALID = "A2UI_OFFICIAL_RESOURCE_INVALID";
    private static final String ERROR_DIGEST_INVALID = "A2UI_OFFICIAL_DIGEST_INVALID";
    private static final String ERROR_CATALOG_INVALID = "A2UI_OFFICIAL_CATALOG_INVALID";
    private static final List<String> COMPONENT_TYPES = List.of(
            "AudioPlayer", "Button", "Card", "CheckBox", "ChoicePicker", "Column",
            "DateTimeInput", "Divider", "Icon", "Image", "List", "Modal", "Row", "Slider",
            "Tabs", "Text", "TextField", "Video");
    private static final List<String> FUNCTION_CODES = List.of(
            "and", "email", "formatCurrency", "formatDate", "formatNumber", "formatString",
            "length", "not", "numeric", "openUrl", "or", "pluralize", "regex", "required");
    private static final Map<String, OfficialDocument> PROTOCOL_DOCUMENTS = protocolDocuments();

    /**
     * 加载并验证完整锁定快照；返回值尚未写 Registry 或 shared release。
     */
    public OfficialBasicCatalogSnapshot loadLockedSnapshot(String operator) {
        String catalogJson = readResource(CATALOG_RESOURCE);
        String rulesText = readResource(RULES_RESOURCE);
        requireDigest(CATALOG_RESOURCE, catalogJson, CATALOG_DIGEST);
        requireDigest(RULES_RESOURCE, rulesText, RULES_DIGEST);
        Map<String, String> protocolDigests = validateProtocolDocuments();
        Map<String, Object> manifest = jsonObject(catalogJson);
        Map<String, Object> components = objectMap(manifest.get("components"));
        Map<String, Object> functions = objectMap(manifest.get("functions"));
        requireCatalogTruth(manifest, components, functions);

        List<ComponentAsset> atoms = new ArrayList<>();
        for (String componentType : COMPONENT_TYPES) {
            atoms.add(atom(componentType, objectMap(components.get(componentType)), operator));
        }
        return new OfficialBasicCatalogSnapshot(
                catalog(manifest, rulesText, protocolDigests, operator), atoms);
    }

    private ComponentAsset catalog(Map<String, Object> manifest, String rulesText,
            Map<String, String> protocolDigests, String operator) {
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("catalogId", CATALOG_ID);
        source.put("nameCn", "A2UI Official Basic Catalog");
        source.put("description", "A2UI v0.9.1 Official Basic locked snapshot");
        source.put("protocolVersion", PROTOCOL_VERSION);
        source.put("catalogSourceType", A2uiCatalogSourceType.A2UI_OFFICIAL.name());
        source.put("sourceCommit", SOURCE_COMMIT);
        source.put("catalogDigest", DIGEST_PREFIX + CATALOG_DIGEST);
        source.put("rulesDigest", DIGEST_PREFIX + RULES_DIGEST);
        source.put("protocolDigests", protocolDigests);
        source.put("componentCodes", COMPONENT_TYPES);
        source.put("functionCodes", FUNCTION_CODES);
        source.put("officialCatalogManifest", manifest);
        source.put("officialRulesText", rulesText);
        String canonicalSource = JsonSupport.toJSON(A2uiImmutableJsonSupport.canonicalize(source));
        return new ComponentAsset()
                .setAssetType(ASSET_TYPE_CATALOG)
                .setComponentName(CATALOG_ID)
                .setComponentNameCn("A2UI Official Basic Catalog")
                .setRuntimeConfigJson(canonicalSource)
                .setEnabled(Boolean.TRUE)
                .setOperator(operator);
    }

    private ComponentAsset atom(String componentType, Map<String, Object> officialSchema,
            String operator) {
        Map<String, Object> contract = new LinkedHashMap<>();
        contract.put("componentCode", componentType);
        contract.put("type", componentType);
        contract.put("componentOriginType", A2uiComponentOriginType.A2UI_OFFICIAL.name());
        contract.put("nameCn", componentType);
        contract.put("category", "OFFICIAL_BASIC");
        contract.put("compositionKind", "ATOMIC");
        contract.put("officialCatalogId", CATALOG_ID);
        contract.put("officialSourceCommit", SOURCE_COMMIT);
        contract.put("officialSchema", officialSchema);
        Map<String, Object> canonicalContract = jsonObject(
                JsonSupport.toJSON(A2uiImmutableJsonSupport.canonicalize(contract)));
        return new ComponentAsset()
                .setAssetType(ASSET_TYPE_ATOM)
                .setComponentName(componentType)
                .setComponentNameCn(componentType)
                .setA2uiComponentType(componentType)
                .setA2uiContract(canonicalContract)
                .setProtocolVersion(1)
                .setEnabled(Boolean.TRUE)
                .setOperator(operator);
    }

    private Map<String, String> validateProtocolDocuments() {
        Map<String, String> digests = new LinkedHashMap<>();
        PROTOCOL_DOCUMENTS.forEach((name, document) -> {
            String content = readResource(document.resource());
            requireDigest(document.resource(), content, document.digest());
            jsonObject(content);
            digests.put(name, DIGEST_PREFIX + document.digest());
        });
        return digests;
    }

    private void requireCatalogTruth(Map<String, Object> manifest, Map<String, Object> components,
            Map<String, Object> functions) {
        if (!CATALOG_ID.equals(manifest.get("catalogId"))
                || !new TreeSet<>(COMPONENT_TYPES).equals(new TreeSet<>(components.keySet()))
                || !new TreeSet<>(FUNCTION_CODES).equals(new TreeSet<>(functions.keySet()))) {
            throw new IllegalStateException(ERROR_CATALOG_INVALID);
        }
        if (components.size() != COMPONENT_TYPES.size() || functions.size() != FUNCTION_CODES.size()) {
            throw new IllegalStateException(ERROR_CATALOG_INVALID);
        }
    }

    private void requireDigest(String resource, String content, String expected) {
        String actual = ReleaseDigestUtils.sha256(content);
        if (!expected.equals(actual)) {
            throw new IllegalStateException(ERROR_DIGEST_INVALID + ":" + resource);
        }
    }

    private String readResource(String resource) {
        ClassLoader loader = A2uiOfficialBasicCatalogImporter.class.getClassLoader();
        try (InputStream input = loader.getResourceAsStream(resource)) {
            if (input == null) {
                throw new IllegalStateException(ERROR_RESOURCE_INVALID + ":" + resource);
            }
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException exception) {
            throw new IllegalStateException(ERROR_RESOURCE_INVALID + ":" + resource, exception);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> jsonObject(String json) {
        Object value = JsonSupport.fromJSON(json, Object.class);
        if (!(value instanceof Map)) {
            throw new IllegalStateException(ERROR_RESOURCE_INVALID);
        }
        return (Map<String, Object>) value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> objectMap(Object value) {
        if (!(value instanceof Map)) {
            throw new IllegalStateException(ERROR_CATALOG_INVALID);
        }
        return (Map<String, Object>) value;
    }

    private static Map<String, OfficialDocument> protocolDocuments() {
        Map<String, OfficialDocument> documents = new LinkedHashMap<>();
        documents.put("serverToClient", document("server_to_client.json",
                "da75d25378b0d02069cc3de54db76f6f71cffdf2a3fd95a8fabbb1f516c07cbe"));
        documents.put("clientToServer", document("client_to_server.json",
                "76c9a6f54e40bbcc1ed7b36b0d56563b82122ea7f9d8379787c4afcf29cc95e0"));
        documents.put("commonTypes", document("common_types.json",
                "ac79788e95e5bdf0a39808953593a53c1bc9fcdcdb55480f4610613c6591e94c"));
        documents.put("clientCapabilities", document("client_capabilities.json",
                "917ff302b883c8c50475f0fafa836c17620078e7e2089392b322dc5df01de78f"));
        documents.put("serverCapabilities", document("server_capabilities.json",
                "bdaf275dd2abf279e62637ead1b840744e031d94735ec4f63d0c7c2fe5347dd4"));
        documents.put("clientDataModel", document("client_data_model.json",
                "a2d9301eda70f71be089a6fae09428ed9fab9fcc23775e2cd227e220419ef6cd"));
        return Collections.unmodifiableMap(documents);
    }

    private static OfficialDocument document(String fileName, String digest) {
        return new OfficialDocument(RESOURCE_ROOT + "json/" + fileName, digest);
    }

    private record OfficialDocument(String resource, String digest) {
    }

    /**
     * 校验完成但尚未写库/发布的 Official Catalog 与 atom 集合。
     */
    public static final class OfficialBasicCatalogSnapshot {

        private final ComponentAsset catalogAsset;
        private final List<ComponentAsset> atomAssets;

        private OfficialBasicCatalogSnapshot(ComponentAsset catalogAsset,
                List<ComponentAsset> atomAssets) {
            this.catalogAsset = catalogAsset;
            this.atomAssets = Collections.unmodifiableList(new ArrayList<>(atomAssets));
        }

        public ComponentAsset getCatalogAsset() {
            return catalogAsset;
        }

        public List<ComponentAsset> getAtomAssets() {
            return atomAssets;
        }
    }
}
