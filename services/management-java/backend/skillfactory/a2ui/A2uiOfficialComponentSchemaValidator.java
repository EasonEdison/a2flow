package dev.a2flow.management.skillfactory.a2ui;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.networknt.schema.Schema;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;

import dev.a2flow.management.a2ui.registry.A2uiComponentOriginType;
import dev.a2flow.management.support.JsonSupport;

/**
 * Validates official component instances against the locally locked Google A2UI schemas.
 *
 * <p>The registry contains only the bundled Basic Catalog and common-types document. Project-owned
 * components are outside this validator; callers select official instances using the compiled
 * component-origin map.</p>
 */
public final class A2uiOfficialComponentSchemaValidator {

    private static final String DRAFT_2020_12 =
            "https://json-schema.org/draft/2020-12/schema";
    private static final String OFFICIAL_CATALOG_ID =
            "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json";
    private static final String OFFICIAL_COMMON_TYPES_ID =
            "https://a2ui.org/specification/v0_9/common_types.json";
    private static final String OFFICIAL_CATALOG_REFERENCE_ID =
            "https://a2ui.org/specification/v0_9/catalog.json";
    private static final String RESOURCE_ROOT = "skillfactory/a2ui/v0_9_1/official/";
    private static final String FIELD_UPDATE_COMPONENTS = "updateComponents";
    private static final String FIELD_COMPONENTS = "components";
    private static final String FIELD_COMPONENT = "component";
    private static final Map<String, Schema> COMPONENT_SCHEMAS = componentSchemas();

    /** Validates every official component in a protocol message batch. */
    public void validateMessages(List<Map<String, Object>> messages,
            Map<String, A2uiComponentOriginType> componentOrigins) {
        if (messages == null || componentOrigins == null) {
            throw invalid();
        }
        for (Map<String, Object> message : messages) {
            if (message == null
                    || !(message.get(FIELD_UPDATE_COMPONENTS) instanceof Map<?, ?> update)) {
                continue;
            }
            Object rawComponents = update.get(FIELD_COMPONENTS);
            if (!(rawComponents instanceof List<?> components)) {
                throw invalid();
            }
            for (Object rawComponent : components) {
                Map<String, Object> component = stringMap(rawComponent);
                String type = text(component.get(FIELD_COMPONENT));
                if (type == null) {
                    throw invalid();
                }
                if (componentOrigins.get(type) == A2uiComponentOriginType.A2UI_OFFICIAL) {
                    validateOfficial(type, component);
                }
            }
        }
    }

    private void validateOfficial(String type, Map<String, Object> component) {
        Schema schema = COMPONENT_SCHEMAS.get(type);
        if (schema == null) {
            throw invalid();
        }
        try {
            if (!schema.validate(JsonSupport.mapper().valueToTree(component)).isEmpty()) {
                throw invalid();
            }
        } catch (RuntimeException exception) {
            throw invalid();
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Schema> componentSchemas() {
        String catalogJson = readResource(RESOURCE_ROOT + "basic/catalog.json");
        String commonTypesJson = readResource(RESOURCE_ROOT + "json/common_types.json");
        Map<String, String> documents = new LinkedHashMap<>();
        documents.put(OFFICIAL_CATALOG_ID, catalogJson);
        // common_types.json resolves its relative catalog.json function reference here.
        documents.put(OFFICIAL_CATALOG_REFERENCE_ID, catalogJson);
        documents.put(OFFICIAL_COMMON_TYPES_ID, commonTypesJson);
        SchemaRegistry registry = SchemaRegistry.withDefaultDialect(
                SpecificationVersion.DRAFT_2020_12, builder -> {
                    builder.schemaLoader(loader -> loader.fetchRemoteResources(false));
                    builder.schemas(documents);
                });
        Map<String, Object> catalog = JsonSupport.fromJSON(catalogJson, Map.class);
        Map<String, Object> definitions = stringMap(catalog.get(FIELD_COMPONENTS));
        Map<String, Schema> schemas = new LinkedHashMap<>();
        for (String type : definitions.keySet()) {
            String escapedType = type.replace("~", "~0").replace("/", "~1");
            Map<String, Object> reference = Map.of(
                    "$schema", DRAFT_2020_12,
                    "$ref", OFFICIAL_CATALOG_ID + "#/components/" + escapedType);
            schemas.put(type, registry.getSchema(JsonSupport.mapper().valueToTree(reference)));
        }
        return Collections.unmodifiableMap(schemas);
    }

    private static String readResource(String resource) {
        try (InputStream input = A2uiOfficialComponentSchemaValidator.class
                .getClassLoader().getResourceAsStream(resource)) {
            if (input == null) {
                throw invalid();
            }
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException exception) {
            throw invalid();
        }
    }

    private static Map<String, Object> stringMap(Object value) {
        if (!(value instanceof Map<?, ?> raw)) {
            throw invalid();
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw invalid();
            }
            result.put(key, entry.getValue());
        }
        return result;
    }

    private static String text(Object value) {
        if (!(value instanceof String text) || text.trim().isEmpty()) {
            return null;
        }
        return text.trim();
    }

    private static ValidationException invalid() {
        return new ValidationException();
    }

    /** Stable fail-closed signal; component payloads are deliberately not included. */
    public static final class ValidationException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        private ValidationException() {
            super("A2UI_OFFICIAL_COMPONENT_INVALID");
        }
    }
}
