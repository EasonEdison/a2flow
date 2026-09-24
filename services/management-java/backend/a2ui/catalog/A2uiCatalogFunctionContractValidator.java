package dev.a2flow.management.a2ui.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import org.apache.commons.lang3.StringUtils;

import com.networknt.schema.Schema;
import com.networknt.schema.SchemaLocation;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;
import com.networknt.schema.dialect.Dialect;
import com.networknt.schema.dialect.Dialects;
import com.networknt.schema.keyword.NonValidationKeyword;

import dev.a2flow.management.a2ui.registry.A2uiRegistryValidationException;
import dev.a2flow.management.support.JsonSupport;

/**
 * A2UI Catalog 函数合同的通用、无脚本校验器。
 *
 * <p>项目 Catalog 只能声明 JSON Schema；解析器不下载远端 schema，只注册随 M 二进制锁定的
 * Official Basic Catalog/common types 与项目合同自身。Application 发布时只使用目标环境已发布
 * Catalog 内的函数集合，并仅递归检查 updateComponents 的组件协议表达式，避免把业务数据中普通
 * 的 call 字段误判为 FunctionCall。
 */
public final class A2uiCatalogFunctionContractValidator {

    private static final String DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema";
    private static final String OFFICIAL_CATALOG_ID =
            "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json";
    private static final String OFFICIAL_COMMON_TYPES_ID =
            "https://a2ui.org/specification/v0_9/common_types.json";
    private static final String CATALOG_ALIAS_ID =
            "https://a2ui.org/specification/v0_9/catalog.json";
    private static final String OFFICIAL_ROOT = "skillfactory/a2ui/v0_9_1/official/";
    private static final String FIELD_SCHEMA = "$schema";
    private static final String FIELD_ID = "$id";
    private static final String FIELD_CATALOG_ID = "catalogId";
    private static final String FIELD_FUNCTIONS = "functions";
    private static final String FIELD_FUNCTION_CONTRACT = "functionContract";
    private static final String FIELD_OFFICIAL_MANIFEST = "officialCatalogManifest";
    private static final String FIELD_CATALOG_MANIFEST = "catalogManifest";
    private static final String FIELD_CALL = "call";
    private static final String FIELD_ARGS = "args";
    private static final String FIELD_RETURN_TYPE = "returnType";
    private static final String FIELD_UPDATE_COMPONENTS = "updateComponents";
    private static final String FIELD_COMPONENTS = "components";
    private static final String ERROR_CONTRACT_INVALID = "A2UI_CATALOG_FUNCTION_CONTRACT_INVALID";
    private static final String ERROR_CALL_INVALID = "A2UI_APPLICATION_FUNCTION_CALL_INVALID";
    private static final int MAX_CONTRACT_BYTES = 512 * 1024;
    private static final int MAX_FUNCTIONS = 128;
    private static final int MAX_EXPRESSION_DEPTH = 64;
    private static final int MAX_EXPRESSION_NODES = 20_000;
    private static final Set<String> FUNCTION_CALL_FIELDS =
            Set.of(FIELD_CALL, FIELD_ARGS, FIELD_RETURN_TYPE);
    private static final String OFFICIAL_CATALOG_JSON =
            readResource(OFFICIAL_ROOT + "basic/catalog.json");
    private static final String OFFICIAL_COMMON_TYPES_JSON =
            readResource(OFFICIAL_ROOT + "json/common_types.json");
    private static final Schema META_SCHEMA = SchemaRegistry
            .withDefaultDialect(SpecificationVersion.DRAFT_2020_12)
            .getSchema(SchemaLocation.of(DRAFT_2020_12));

    /** 校验普通项目 Catalog 提交的完整函数合同，并返回服务端派生字段。 */
    public ValidatedFunctionContract validateProjectContract(
            String expectedCatalogId, Object rawContract) {
        Map<String, Object> contract = objectMap(rawContract, ERROR_CONTRACT_INVALID);
        return validateContract(expectedCatalogId, contract, false);
    }

    /** 校验 locked Official manifest 的 14 个函数，不要求额外伪造 functionContract 包装。 */
    public ValidatedFunctionContract validateOfficialManifest(Object rawManifest) {
        Map<String, Object> manifest = objectMap(rawManifest, ERROR_CONTRACT_INVALID);
        if (!OFFICIAL_CATALOG_ID.equals(text(manifest.get(FIELD_ID)))
                || !OFFICIAL_CATALOG_ID.equals(text(manifest.get(FIELD_CATALOG_ID)))) {
            throw invalidContract();
        }
        return validateContract(OFFICIAL_CATALOG_ID, manifest, true);
    }

    /**
     * 从发布 Catalog 快照恢复函数 authority。无函数声明的 Catalog 合法，但出现函数调用时会拒绝。
     */
    public ValidatedFunctionContract publishedContract(
            String expectedCatalogId, Map<String, Object> catalogPayload) {
        if (catalogPayload == null) {
            throw invalidContract();
        }
        if (catalogPayload.containsKey(FIELD_FUNCTION_CONTRACT)) {
            return validateProjectContract(
                    expectedCatalogId, catalogPayload.get(FIELD_FUNCTION_CONTRACT));
        }
        if (catalogPayload.containsKey(FIELD_OFFICIAL_MANIFEST)) {
            return validateOfficialManifest(catalogPayload.get(FIELD_OFFICIAL_MANIFEST));
        }
        if (catalogPayload.containsKey(FIELD_CATALOG_MANIFEST)) {
            Map<String, Object> manifest = objectMap(
                    catalogPayload.get(FIELD_CATALOG_MANIFEST), ERROR_CONTRACT_INVALID);
            return validateContract(expectedCatalogId, manifest, true);
        }
        if (catalogPayload.containsKey(FIELD_FUNCTIONS)) {
            throw invalidContract();
        }
        return ValidatedFunctionContract.empty(expectedCatalogId);
    }

    /** 只扫描 A2UI updateComponents.components 内的协议表达式，并递归校验嵌套 FunctionCall。 */
    public void validateMessageTemplateCalls(List<Map<String, Object>> messageTemplates,
            ValidatedFunctionContract contract) {
        if (messageTemplates == null) {
            return;
        }
        int[] visited = new int[] {0};
        for (Map<String, Object> message : messageTemplates) {
            if (message == null) {
                continue;
            }
            Object update = message.get(FIELD_UPDATE_COMPONENTS);
            if (!(update instanceof Map<?, ?> updateMap)) {
                continue;
            }
            Object components = updateMap.get(FIELD_COMPONENTS);
            if (!(components instanceof List<?> componentList)) {
                throw invalidCall();
            }
            for (Object component : componentList) {
                validateExpression(component, contract, 0, visited);
            }
        }
    }

    private ValidatedFunctionContract validateContract(String expectedCatalogId,
            Map<String, Object> contract, boolean trustedManifest) {
        if (StringUtils.isBlank(expectedCatalogId)
                || !DRAFT_2020_12.equals(text(contract.get(FIELD_SCHEMA)))) {
            throw invalidContract();
        }
        String contractId = text(contract.get(FIELD_ID));
        String catalogId = text(contract.get(FIELD_CATALOG_ID));
        if (StringUtils.isAnyBlank(contractId, catalogId)
                || !expectedCatalogId.equals(catalogId)
                || (!trustedManifest && Set.of(
                        OFFICIAL_CATALOG_ID, OFFICIAL_COMMON_TYPES_ID, CATALOG_ALIAS_ID)
                        .contains(contractId))
                || JsonSupport.toJSON(contract).getBytes(StandardCharsets.UTF_8).length
                > MAX_CONTRACT_BYTES) {
            throw invalidContract();
        }
        Map<String, Object> functions = objectMap(
                contract.get(FIELD_FUNCTIONS), ERROR_CONTRACT_INVALID);
        if (functions.isEmpty() || functions.size() > MAX_FUNCTIONS) {
            throw invalidContract();
        }
        validateReferences(contract, contractId, true, 0, new int[] {0});
        for (Map.Entry<String, Object> entry : functions.entrySet()) {
            if (StringUtils.isBlank(entry.getKey()) || !(entry.getValue() instanceof Map<?, ?>)) {
                throw invalidContract();
            }
            validateSchemaStructure(objectMap(entry.getValue(), ERROR_CONTRACT_INVALID));
        }
        if (trustedManifest && OFFICIAL_CATALOG_ID.equals(contractId)
                && !sameJson(functions, officialFunctions())) {
            throw invalidContract();
        }
        Map<String, String> schemas = new LinkedHashMap<>();
        schemas.put(OFFICIAL_CATALOG_ID, OFFICIAL_CATALOG_JSON);
        schemas.put(OFFICIAL_COMMON_TYPES_ID, OFFICIAL_COMMON_TYPES_JSON);
        schemas.put(contractId, JsonSupport.toJSON(contract));
        schemas.put(CATALOG_ALIAS_ID, JsonSupport.toJSON(contract));
        SchemaRegistry registry = SchemaRegistry.withDefaultDialect(
                a2uiDialect(), builder -> builder.schemas(schemas));
        return new ValidatedFunctionContract(
                contractId,
                Collections.unmodifiableMap(new LinkedHashMap<>(contract)),
                Collections.unmodifiableMap(new LinkedHashMap<>(functions)),
                Collections.unmodifiableList(new ArrayList<>(new TreeSet<>(functions.keySet()))),
                registry);
    }

    private void validateExpression(Object value, ValidatedFunctionContract contract,
            int depth, int[] visited) {
        if (depth > MAX_EXPRESSION_DEPTH || ++visited[0] > MAX_EXPRESSION_NODES) {
            throw invalidCall();
        }
        if (value instanceof Map<?, ?> rawMap) {
            Map<String, Object> map = stringKeyMap(rawMap, ERROR_CALL_INVALID);
            if (map.containsKey(FIELD_CALL)) {
                validateFunctionCall(map, contract);
            }
            for (Object child : map.values()) {
                validateExpression(child, contract, depth + 1, visited);
            }
        } else if (value instanceof List<?> list) {
            for (Object child : list) {
                validateExpression(child, contract, depth + 1, visited);
            }
        }
    }

    private void validateFunctionCall(Map<String, Object> call,
            ValidatedFunctionContract contract) {
        if (!FUNCTION_CALL_FIELDS.containsAll(call.keySet())
                || !call.keySet().containsAll(Set.of(FIELD_CALL, FIELD_ARGS))) {
            throw invalidCall();
        }
        String functionCode = text(call.get(FIELD_CALL));
        if (contract == null || StringUtils.isBlank(functionCode)
                || !contract.functions().containsKey(functionCode)) {
            throw invalidCall();
        }
        String pointer = functionCode.replace("~", "~0").replace("/", "~1");
        try {
            Schema schema = contract.registry().getSchema(JsonSupport.mapper().valueToTree(Map.of(
                    FIELD_SCHEMA, DRAFT_2020_12,
                    "$ref", contract.contractId() + "#/functions/" + pointer)));
            if (!schema.validate(JsonSupport.mapper().valueToTree(call)).isEmpty()) {
                throw invalidCall();
            }
        } catch (A2uiRegistryValidationException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw invalidCall();
        }
    }

    private void validateReferences(Object value, String contractId, boolean root,
            int depth, int[] visited) {
        if (depth > MAX_EXPRESSION_DEPTH || ++visited[0] > MAX_EXPRESSION_NODES) {
            throw invalidContract();
        }
        if (value instanceof Map<?, ?> rawMap) {
            Map<String, Object> map = stringKeyMap(rawMap, ERROR_CONTRACT_INVALID);
            if (!root && map.containsKey(FIELD_ID)) {
                throw invalidContract();
            }
            if (map.containsKey("$dynamicRef")) {
                throw invalidContract();
            }
            Object reference = map.get("$ref");
            if (reference != null && !allowedReference(text(reference), contractId)) {
                throw invalidContract();
            }
            for (Object child : map.values()) {
                validateReferences(child, contractId, false, depth + 1, visited);
            }
        } else if (value instanceof List<?> list) {
            for (Object child : list) {
                validateReferences(child, contractId, false, depth + 1, visited);
            }
        }
    }

    private boolean allowedReference(String reference, String contractId) {
        return StringUtils.isNotBlank(reference)
                && (reference.startsWith("#/")
                || reference.startsWith(contractId + "#/")
                || reference.startsWith(OFFICIAL_CATALOG_ID + "#/")
                || reference.startsWith(OFFICIAL_COMMON_TYPES_ID + "#/"));
    }

    private void validateSchemaStructure(Map<String, Object> schema) {
        try {
            if (!META_SCHEMA.validate(JsonSupport.mapper().valueToTree(schema)).isEmpty()) {
                throw invalidContract();
            }
        } catch (A2uiRegistryValidationException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw invalidContract();
        }
    }

    private Map<String, Object> officialFunctions() {
        return objectMap(objectMap(
                JsonSupport.fromJSON(OFFICIAL_CATALOG_JSON, Object.class), ERROR_CONTRACT_INVALID)
                .get(FIELD_FUNCTIONS), ERROR_CONTRACT_INVALID);
    }

    private boolean sameJson(Object left, Object right) {
        return JsonSupport.mapper().valueToTree(left).equals(JsonSupport.mapper().valueToTree(right));
    }

    private Dialect a2uiDialect() {
        return Dialect.builder(Dialects.getDraft202012())
                .keyword(new NonValidationKeyword("catalogId"))
                .keyword(new NonValidationKeyword("functions"))
                .keyword(new NonValidationKeyword("components"))
                .keyword(new NonValidationKeyword("discriminator"))
                .keyword(new NonValidationKeyword("baseCatalog"))
                .keyword(new NonValidationKeyword("sdkExtensions"))
                .build();
    }

    private static String readResource(String resource) {
        try (InputStream input = A2uiCatalogFunctionContractValidator.class
                .getClassLoader().getResourceAsStream(resource)) {
            if (input == null) {
                throw new IllegalStateException(ERROR_CONTRACT_INVALID);
            }
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException exception) {
            throw new IllegalStateException(ERROR_CONTRACT_INVALID, exception);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> objectMap(Object value, String error) {
        if (!(value instanceof Map<?, ?>)) {
            throw new A2uiRegistryValidationException(error);
        }
        return stringKeyMap((Map<?, ?>) value, error);
    }

    private Map<String, Object> stringKeyMap(Map<?, ?> raw, String error) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new A2uiRegistryValidationException(error);
            }
            result.put(key, entry.getValue());
        }
        return result;
    }

    private String text(Object value) {
        return value == null ? null : StringUtils.trimToNull(String.valueOf(value));
    }

    private A2uiRegistryValidationException invalidContract() {
        return new A2uiRegistryValidationException(ERROR_CONTRACT_INVALID);
    }

    private A2uiRegistryValidationException invalidCall() {
        return new A2uiRegistryValidationException(ERROR_CALL_INVALID);
    }

    /** 经校验的不可执行函数 schema 集合；registry 只含内置 official 文档和本合同。 */
    public record ValidatedFunctionContract(
            String contractId,
            Map<String, Object> contract,
            Map<String, Object> functions,
            List<String> functionCodes,
            SchemaRegistry registry) {

        private static ValidatedFunctionContract empty(String catalogId) {
            return new ValidatedFunctionContract(
                    "urn:a2flow:catalog:" + catalogId + ":no-functions",
                    Collections.emptyMap(), Collections.emptyMap(), Collections.emptyList(), null);
        }
    }
}
