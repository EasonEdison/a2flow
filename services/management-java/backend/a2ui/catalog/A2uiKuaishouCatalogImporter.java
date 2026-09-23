package dev.a2flow.management.a2ui.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application
        .A2uiImmutableJsonSupport;
import dev.a2flow.management.a2ui.registry
        .A2uiComponentOriginType;
import dev.a2flow.management.a2ui.registry
        .A2uiRegistryValidationException;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import com.networknt.schema.Schema;
import com.networknt.schema.SchemaLocation;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;

import lombok.extern.slf4j.Slf4j;
import okhttp3.HttpUrl;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;

/**
 * 快手 A2UI Catalog 受控导入器。
 *
 * <p>上游是 ADMIN 发起的 Catalog JSON URL 或原始 JSON 导入，下游只输出完成校验但尚未落库的
 * Catalog/atom 当前态。URL 模式严格限制 HTTPS authority、关闭重定向与重试；两种模式都限制
 * 原始字节数并校验完整结构，计算原始摘要供发布审计。该类不接收 Cookie、不记录正文、不写数据库，也不负责 shared release
 * 发布。
 */
@Service
@Slf4j
public class A2uiKuaishouCatalogImporter {

    public static final String CATALOG_ID = "a2flow.digital-employee.pc.v1";
    public static final String PROTOCOL_VERSION = "v0.9.1";
    public static final String SOURCE_HOST = "p2.eckwai.com";
    public static final List<String> COMPONENT_TYPES = List.of(
            "ActionAdvice", "CheckboxLine", "Container", "EmptyStateCard", "GoodsSelector",
            "IconTitle", "InputDate", "InputNumber", "InputText", "InputTextArea", "Markdown",
            "OperateButtons", "SmallGoods", "Tabs", "TaskStatusBar", "Text",
            "TimeRangePicker", "VideoGoodsSelector");
    public static final List<String> FUNCTION_CODES =
            List.of("length", "numeric", "required", "sendMessage");

    private static final String ASSET_TYPE_CATALOG = "A2UI_CATALOG";
    private static final String ASSET_TYPE_ATOM = "A2UI_ATOM";
    private static final String COMPOSITION_ATOMIC = "ATOMIC";
    private static final String CATEGORY = "KUAISHOU_CATALOG";
    private static final String CHILDREN_MODE_NONE = "NONE";
    private static final String CHILDREN_MODE_STATIC = "STATIC_COMPONENT_ID_LIST";
    private static final String FIELD_CATALOG_ID = "catalogId";
    private static final String FIELD_PROTOCOL_VERSION = "x-a2ui-version";
    private static final String FIELD_COMPONENTS = "components";
    private static final String FIELD_FUNCTIONS = "functions";
    private static final String FIELD_PROPERTIES = "properties";
    private static final String FIELD_REQUIRED = "required";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_CONST = "const";
    private static final String FIELD_ENUM = "enum";
    private static final String FIELD_ANY_OF = "anyOf";
    private static final String FIELD_ONE_OF = "oneOf";
    private static final String FIELD_ITEMS = "items";
    private static final String FIELD_MINIMUM = "minimum";
    private static final String FIELD_MIN_ITEMS = "minItems";
    private static final String FIELD_NOT = "not";
    private static final String ERROR_SOURCE_URL_REQUIRED = "A2UI_CATALOG_SOURCE_URL_REQUIRED";
    private static final String ERROR_SOURCE_URL_REJECTED = "A2UI_CATALOG_SOURCE_URL_REJECTED";
    private static final String ERROR_SOURCE_INPUT_INVALID = "A2UI_CATALOG_SOURCE_INPUT_INVALID";
    private static final String ERROR_SOURCE_FETCH_FAILED = "A2UI_CATALOG_SOURCE_FETCH_FAILED";
    private static final String ERROR_SOURCE_REDIRECT_REJECTED =
            "A2UI_CATALOG_SOURCE_REDIRECT_REJECTED";
    private static final String ERROR_SOURCE_TOO_LARGE = "A2UI_CATALOG_SOURCE_TOO_LARGE";
    private static final String ERROR_SOURCE_INVALID = "A2UI_CATALOG_SOURCE_INVALID";
    private static final String SOURCE_MODE_URL = "URL";
    private static final String SOURCE_MODE_INLINE_JSON = "INLINE_JSON";
    private static final int HTTPS_PORT = 443;
    private static final int HTTP_OK = 200;
    private static final int REDIRECT_STATUS_MIN = 300;
    private static final int REDIRECT_STATUS_MAX_EXCLUSIVE = 400;
    private static final int CONNECT_TIMEOUT_MILLIS = 3_000;
    private static final int READ_TIMEOUT_MILLIS = 10_000;
    private static final int CALL_TIMEOUT_MILLIS = 12_000;
    private static final int MAX_RESPONSE_BYTES = 1024 * 1024;
    private static final int MAX_EXAMPLE_DEPTH = 32;
    private static final int MAX_EXAMPLE_NODES = 2000;
    private static final int MAX_EXAMPLE_ARRAY_ITEMS = 100;
    private static final int MAX_EXAMPLE_BYTES = 64 * 1024;
    private static final String META_SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema";
    private static final Schema META_SCHEMA = SchemaRegistry
            .withDefaultDialect(SpecificationVersion.DRAFT_2020_12)
            .getSchema(SchemaLocation.of(META_SCHEMA_URI));

    private final OkHttpClient httpClient = new OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)
            .readTimeout(READ_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)
            .callTimeout(CALL_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .retryOnConnectionFailure(false)
            .build();

    /**
     * 读取并校验完整 URL Catalog 源；网络和 JSON 处理完成后才把快照交给数据库短事务。
     */
    public KuaishouCatalogSnapshot loadSnapshot(String sourceUrl, String operator) {
        HttpUrl target = validateUrl(sourceUrl);
        return validateSnapshot(fetch(target), target.toString(), SOURCE_MODE_URL, operator);
    }

    /**
     * 从 URL 或原始 JSON 二选一读取完整 Catalog 源，统一计算原始摘要并校验结构。
     */
    public KuaishouCatalogSnapshot loadSnapshot(String sourceUrl, String catalogJson,
            String operator) {
        boolean hasSourceUrl = StringUtils.isNotBlank(sourceUrl);
        boolean hasCatalogJson = StringUtils.isNotBlank(catalogJson);
        if (hasSourceUrl == hasCatalogJson) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_INPUT_INVALID);
        }
        if (hasSourceUrl) {
            return loadSnapshot(sourceUrl, operator);
        }
        return validateSnapshot(inlineSourceBytes(catalogJson), null,
                SOURCE_MODE_INLINE_JSON, operator);
    }

    private KuaishouCatalogSnapshot validateSnapshot(byte[] sourceBytes, String sourceUrl,
            String sourceMode, String operator) {
        String rawDigest = sha256(sourceBytes);
        Map<String, Object> manifest = jsonObject(sourceBytes);
        Map<String, Object> components = objectMap(manifest.get(FIELD_COMPONENTS));
        Map<String, Object> functions = objectMap(manifest.get(FIELD_FUNCTIONS));
        validateManifest(manifest, components, functions);

        List<ComponentAsset> atoms = new ArrayList<>();
        for (String componentType : COMPONENT_TYPES) {
            atoms.add(atom(componentType, objectMap(components.get(componentType)), operator));
        }
        ComponentAsset catalog = catalog(manifest, functions, sourceUrl, rawDigest, operator);
        log.info("快手A2UI Catalog受控源校验完成, catalogId:{}, componentCount:{}, functionCount:{}, "
                        + "rawDigest:{}, operator:{}",
                CATALOG_ID, atoms.size(), functions.size(), rawDigest, operator);
        return new KuaishouCatalogSnapshot(catalog, atoms, rawDigest, functions.size());
    }

    private byte[] inlineSourceBytes(String catalogJson) {
        byte[] sourceBytes = catalogJson.getBytes(StandardCharsets.UTF_8);
        if (sourceBytes.length > MAX_RESPONSE_BYTES) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_TOO_LARGE);
        }
        return sourceBytes;
    }

    private HttpUrl validateUrl(String sourceUrl) {
        if (StringUtils.isBlank(sourceUrl)) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_URL_REQUIRED);
        }
        URI uri;
        HttpUrl target;
        try {
            uri = URI.create(StringUtils.trim(sourceUrl));
            target = HttpUrl.parse(uri.toString());
        } catch (RuntimeException exception) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_URL_REJECTED);
        }
        if (target == null || !"https".equalsIgnoreCase(target.scheme())
                || !SOURCE_HOST.equalsIgnoreCase(target.host())
                || target.port() != HTTPS_PORT
                || StringUtils.isNotEmpty(target.username())
                || StringUtils.isNotEmpty(target.password())
                || uri.getRawUserInfo() != null) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_URL_REJECTED);
        }
        return target;
    }

    private byte[] fetch(HttpUrl target) {
        Request request = new Request.Builder().url(target).get().build();
        try (Response response = httpClient.newCall(request).execute()) {
            if (response.code() >= REDIRECT_STATUS_MIN
                    && response.code() < REDIRECT_STATUS_MAX_EXCLUSIVE) {
                throw new A2uiRegistryValidationException(ERROR_SOURCE_REDIRECT_REJECTED);
            }
            if (response.code() != HTTP_OK) {
                throw new A2uiRegistryValidationException(ERROR_SOURCE_FETCH_FAILED);
            }
            ResponseBody body = response.body();
            if (body == null) {
                throw new A2uiRegistryValidationException(ERROR_SOURCE_FETCH_FAILED);
            }
            if (body.contentLength() > MAX_RESPONSE_BYTES) {
                throw new A2uiRegistryValidationException(ERROR_SOURCE_TOO_LARGE);
            }
            try (InputStream input = body.byteStream()) {
                byte[] bytes = input.readNBytes(MAX_RESPONSE_BYTES + 1);
                if (bytes.length > MAX_RESPONSE_BYTES) {
                    throw new A2uiRegistryValidationException(ERROR_SOURCE_TOO_LARGE);
                }
                return bytes;
            }
        } catch (A2uiRegistryValidationException exception) {
            throw exception;
        } catch (IOException exception) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_FETCH_FAILED);
        }
    }

    private ComponentAsset catalog(Map<String, Object> manifest, Map<String, Object> functions,
            String sourceUrl, String rawDigest, String operator) {
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("catalogId", CATALOG_ID);
        source.put("nameCn", valueOrDefault(manifest.get("title"), "快手数字员工PC Catalog"));
        source.put("description", valueOrDefault(manifest.get("description"), StringUtils.EMPTY));
        source.put("protocolVersion", PROTOCOL_VERSION);
        source.put("catalogSourceType", A2uiCatalogSourceType.PLATFORM_MANAGED.name());
        if (StringUtils.isNotBlank(sourceUrl)) {
            source.put("sourceUrl", sourceUrl);
        }
        source.put("rawDigest", rawDigest);
        source.put("componentCodes", COMPONENT_TYPES);
        source.put("functionCodes", FUNCTION_CODES);
        source.put("functions", functions);
        source.put("catalogManifest", manifest);
        String canonicalSource = JsonSupport.toJSON(A2uiImmutableJsonSupport.canonicalize(source));
        return new ComponentAsset()
                .setAssetType(ASSET_TYPE_CATALOG)
                .setComponentName(CATALOG_ID)
                .setComponentNameCn(String.valueOf(source.get("nameCn")))
                .setRuntimeConfigJson(canonicalSource)
                .setEnabled(Boolean.TRUE)
                .setOperator(operator);
    }

    private ComponentAsset atom(String componentType, Map<String, Object> componentSchema,
            String operator) {
        Map<String, Object> contract = new LinkedHashMap<>();
        contract.put("componentCode", componentType);
        contract.put("type", componentType);
        contract.put("componentOriginType", A2uiComponentOriginType.PLATFORM_CUSTOM.name());
        contract.put("nameCn", componentType);
        contract.put("category", CATEGORY);
        contract.put("compositionKind", COMPOSITION_ATOMIC);
        contract.put("propsSchema", componentSchema);
        contract.put("eventSchema", eventSchema(componentSchema));
        contract.put("childrenConstraint", childrenConstraint(componentType));
        contract.put("validMessageExample", minimalValue(componentSchema, componentType, null));
        contract.put("invalidMessageExample", Map.of("id", StringUtils.EMPTY,
                "component", componentType));
        Map<String, Object> canonicalContract = jsonObject(JsonSupport.toJSON(
                A2uiImmutableJsonSupport.canonicalize(contract)).getBytes(StandardCharsets.UTF_8));
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

    private Map<String, Object> eventSchema(Map<String, Object> componentSchema) {
        Map<String, Object> properties = objectMap(componentSchema.get(FIELD_PROPERTIES));
        Map<String, Object> eventProperties = new LinkedHashMap<>();
        Set<String> required = new LinkedHashSet<>(stringList(componentSchema.get(FIELD_REQUIRED)));
        List<String> eventRequired = new ArrayList<>();
        for (Map.Entry<String, Object> property : properties.entrySet()) {
            if (isActionProperty(property.getKey())) {
                eventProperties.put(property.getKey(), property.getValue());
                if (required.contains(property.getKey())) {
                    eventRequired.add(property.getKey());
                }
            }
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_TYPE, "object");
        result.put(FIELD_PROPERTIES, eventProperties);
        if (!eventRequired.isEmpty()) {
            result.put(FIELD_REQUIRED, eventRequired);
        }
        result.put("additionalProperties", false);
        return result;
    }

    private boolean isActionProperty(String propertyName) {
        return "action".equals(propertyName) || "actions".equals(propertyName)
                || (propertyName != null && propertyName.endsWith("Action"));
    }

    private Map<String, Object> childrenConstraint(String componentType) {
        Map<String, Object> result = new LinkedHashMap<>();
        if ("Container".equals(componentType) || "TaskStatusBar".equals(componentType)) {
            result.put("mode", CHILDREN_MODE_STATIC);
            result.put("allowedComponentTypes", COMPONENT_TYPES);
            result.put("minItems", 0);
            result.put("maxItems", 100);
        } else {
            result.put("mode", CHILDREN_MODE_NONE);
            result.put("minItems", 0);
            result.put("maxItems", 0);
        }
        return result;
    }

    private Object minimalValue(Map<String, Object> schema, String componentType, String fieldName) {
        return minimalValue(schema, componentType, fieldName, 0, new int[2]);
    }

    /** 限制示例展开深度、总节点、数组长度和字节预算，防止合法小 schema 产生指数级内存分配。 */
    @SuppressWarnings("unchecked")
    private Object minimalValue(Map<String, Object> schema, String componentType,
            String fieldName, int depth, int[] visited) {
        if (depth > MAX_EXAMPLE_DEPTH || ++visited[0] > MAX_EXAMPLE_NODES) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_TOO_LARGE);
        }
        if (schema.containsKey(FIELD_CONST)) {
            return exampleLiteral(schema.get(FIELD_CONST), visited);
        }
        Object enumValue = schema.get(FIELD_ENUM);
        if (enumValue instanceof List<?> values && !values.isEmpty()) {
            return exampleLiteral(values.get(0), visited);
        }
        Map<String, Object> branch = firstPositiveBranch(schema.get(FIELD_ANY_OF));
        if (branch == null) {
            branch = firstPositiveBranch(schema.get(FIELD_ONE_OF));
        }
        if (branch != null) {
            return minimalValue(branch, componentType, fieldName, depth + 1, visited);
        }
        String type = String.valueOf(schema.get(FIELD_TYPE));
        if ("object".equals(type)) {
            Map<String, Object> result = new LinkedHashMap<>();
            Map<String, Object> properties = schema.get(FIELD_PROPERTIES) instanceof Map
                    ? (Map<String, Object>) schema.get(FIELD_PROPERTIES) : Collections.emptyMap();
            for (String requiredField : stringList(schema.get(FIELD_REQUIRED))) {
                exampleLiteral(requiredField, visited);
                Object child = properties.get(requiredField);
                if (!(child instanceof Map)) {
                    throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
                }
                result.put(requiredField, minimalValue((Map<String, Object>) child,
                        componentType, requiredField, depth + 1, visited));
            }
            return result;
        }
        if ("array".equals(type)) {
            Object rawMinItems = schema.get(FIELD_MIN_ITEMS);
            if (rawMinItems instanceof Number
                    && ((Number) rawMinItems).doubleValue() > MAX_EXAMPLE_ARRAY_ITEMS) {
                throw new A2uiRegistryValidationException(ERROR_SOURCE_TOO_LARGE);
            }
            int minItems = integer(schema.get(FIELD_MIN_ITEMS));
            if (minItems <= 0) {
                return new ArrayList<>();
            }
            Object itemSchema = schema.get(FIELD_ITEMS);
            if (!(itemSchema instanceof Map)) {
                throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
            }
            List<Object> values = new ArrayList<>();
            for (int index = 0; index < minItems; index++) {
                values.add(minimalValue((Map<String, Object>) itemSchema, componentType,
                        fieldName, depth + 1, visited));
            }
            return values;
        }
        if ("integer".equals(type) || "number".equals(type)) {
            Object minimum = schema.get(FIELD_MINIMUM);
            return minimum instanceof Number ? minimum : 0;
        }
        if ("boolean".equals(type)) {
            return false;
        }
        if ("null".equals(type)) {
            return null;
        }
        if ("string".equals(type)) {
            if ("id".equals(fieldName)) {
                return componentType + "-example";
            }
            return "example";
        }
        throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
    }

    /** 每次复用 literal 都计入输出预算，在拼装或最终序列化大样例之前拒绝放大输入。 */
    private Object exampleLiteral(Object value, int[] visited) {
        int bytes = JsonSupport.toJSON(value).getBytes(StandardCharsets.UTF_8).length;
        if (bytes > MAX_EXAMPLE_BYTES - visited[1]) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_TOO_LARGE);
        }
        visited[1] += bytes;
        return value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> firstPositiveBranch(Object value) {
        if (!(value instanceof List<?> branches)) {
            return null;
        }
        for (Object branch : branches) {
            if (branch instanceof Map && !((Map<String, Object>) branch).containsKey(FIELD_NOT)) {
                return (Map<String, Object>) branch;
            }
        }
        return null;
    }

    private void validateManifest(Map<String, Object> manifest, Map<String, Object> components,
            Map<String, Object> functions) {
        if (!CATALOG_ID.equals(manifest.get(FIELD_CATALOG_ID))
                || !PROTOCOL_VERSION.equals(manifest.get(FIELD_PROTOCOL_VERSION))
                || !new LinkedHashSet<>(COMPONENT_TYPES).equals(components.keySet())
                || !new LinkedHashSet<>(FUNCTION_CODES).equals(functions.keySet())) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
        }
        for (String componentType : COMPONENT_TYPES) {
            Map<String, Object> schema = objectMap(components.get(componentType));
            validateSchemaStructure(schema);
            Map<String, Object> properties = objectMap(schema.get(FIELD_PROPERTIES));
            if (!"object".equals(schema.get(FIELD_TYPE))
                    || !properties.containsKey("id") || !properties.containsKey("component")
                    || !componentType.equals(objectMap(properties.get("component")).get(FIELD_CONST))) {
                throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
            }
        }
        for (String functionCode : FUNCTION_CODES) {
            validateSchemaStructure(objectMap(functions.get(functionCode)));
        }
    }

    /** 复用项目 NetworkNT 内置元 schema 校验可选属性与嵌套 schema；不解析用户 schema 的远端引用。 */
    private void validateSchemaStructure(Map<String, Object> schema) {
        try {
            if (!META_SCHEMA.validate(JsonSupport.mapper().valueToTree(schema)).isEmpty()) {
                throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
            }
        } catch (RuntimeException exception) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> jsonObject(byte[] bytes) {
        try {
            Object value = JsonSupport.fromJSON(new String(bytes, StandardCharsets.UTF_8), Object.class);
            if (!(value instanceof Map)) {
                throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
            }
            return (Map<String, Object>) value;
        } catch (A2uiRegistryValidationException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> objectMap(Object value) {
        if (!(value instanceof Map)) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
        }
        return (Map<String, Object>) value;
    }

    private List<String> stringList(Object value) {
        if (!(value instanceof List<?> values)) {
            return Collections.emptyList();
        }
        List<String> result = new ArrayList<>();
        for (Object item : values) {
            String text = item == null ? null : StringUtils.trimToNull(String.valueOf(item));
            if (text == null) {
                throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
            }
            result.add(text);
        }
        return result;
    }

    private int integer(Object value) {
        return value instanceof Number ? ((Number) value).intValue() : 0;
    }

    private String valueOrDefault(Object value, String fallback) {
        return StringUtils.defaultIfBlank(value == null ? null : String.valueOf(value), fallback);
    }

    private String sha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder result = new StringBuilder(digest.length * 2);
            for (byte value : digest) {
                result.append(String.format("%02x", value & 0xff));
            }
            return result.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(ERROR_SOURCE_INVALID, exception);
        }
    }

    /** 完成网络和结构校验、等待原子写入的快照。 */
    public static final class KuaishouCatalogSnapshot {

        private final ComponentAsset catalogAsset;
        private final List<ComponentAsset> atomAssets;
        private final String rawDigest;
        private final int functionCount;

        private KuaishouCatalogSnapshot(ComponentAsset catalogAsset,
                List<ComponentAsset> atomAssets, String rawDigest, int functionCount) {
            this.catalogAsset = catalogAsset;
            this.atomAssets = Collections.unmodifiableList(new ArrayList<>(atomAssets));
            this.rawDigest = rawDigest;
            this.functionCount = functionCount;
        }

        public ComponentAsset getCatalogAsset() {
            return catalogAsset;
        }

        public List<ComponentAsset> getAtomAssets() {
            return atomAssets;
        }

        public String getRawDigest() {
            return rawDigest;
        }

        public int getFunctionCount() {
            return functionCount;
        }
    }
}
