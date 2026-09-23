package dev.a2flow.management.support;

import java.util.Map;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;

/** Shared public Jackson codec; invalid JSON fails explicitly. */
public final class JsonSupport {
    private static final ObjectMapper MAPPER = JsonMapper.builder().findAndAddModules().build();
    private JsonSupport() { }
    public static ObjectMapper mapper() { return MAPPER; }
    public static String toJSON(Object value) {
        try { return MAPPER.writeValueAsString(value); }
        catch (JsonProcessingException e) { throw new IllegalArgumentException("JSON serialization failed", e); }
    }
    public static <T> T fromJSON(String json, Class<T> type) {
        try { return MAPPER.readValue(json, type); }
        catch (JsonProcessingException e) { throw new IllegalArgumentException("JSON parsing failed", e); }
    }
    public static <T> T fromJSON(String json, Class<T> type, Class<?>... parameters) {
        try { return MAPPER.readValue(json, MAPPER.getTypeFactory().constructParametricType(type, parameters)); }
        catch (JsonProcessingException e) { throw new IllegalArgumentException("JSON parsing failed", e); }
    }
    @SuppressWarnings("unchecked")
    public static Map<String, Object> fromJson(String json) { return fromJSON(json, Map.class); }
}
