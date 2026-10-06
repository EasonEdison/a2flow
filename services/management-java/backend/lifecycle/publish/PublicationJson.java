package dev.a2flow.management.lifecycle.publish;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.TreeMap;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

/** Python asset-store compatible canonical UTF-8 JSON. */
final class PublicationJson {
    static final int MAX_BYTES = 16 * 1024 * 1024;
    private static final ObjectMapper JSON = new ObjectMapper().enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
            .enable(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    private PublicationJson() { }
    static JsonNode parse(String value) throws IOException {
        try {
            if (value == null || value.getBytes(StandardCharsets.UTF_8).length > MAX_BYTES) throw failure("BUNDLE_TOO_LARGE");
            JsonNode result = JSON.readTree(value);
            if (result == null || result.isMissingNode()) throw failure("INVALID_JSON");
            return result;
        } catch (IOException exception) { throw failure("INVALID_JSON"); }
    }
    static ObjectNode object(Object... pairs) {
        ObjectNode node = JSON.createObjectNode();
        for (int index = 0; index < pairs.length; index += 2) node.set((String) pairs[index], JSON.valueToTree(pairs[index + 1]));
        return node;
    }
    static ArrayNode array(Object... items) {
        ArrayNode node = JSON.createArrayNode();
        for (Object item : items) node.add(JSON.valueToTree(item));
        return node;
    }
    static byte[] bytes(JsonNode node) throws IOException {
        StringBuilder output = new StringBuilder();
        append(node, output);
        byte[] result = output.toString().getBytes(StandardCharsets.UTF_8);
        if (result.length > MAX_BYTES) throw failure("BUNDLE_TOO_LARGE");
        return result;
    }
    private static void append(JsonNode node, StringBuilder output) throws IOException {
        if (node == null || node.isNull()) { output.append("null"); return; }
        if (node.isObject()) {
            TreeMap<String, JsonNode> fields = new TreeMap<>((left, right) -> {
                int[] a = left.codePoints().toArray(), b = right.codePoints().toArray();
                for (int index = 0; index < Math.min(a.length, b.length); index++) if (a[index] != b[index]) return Integer.compare(a[index], b[index]);
                return Integer.compare(a.length, b.length);
            });
            node.fields().forEachRemaining(entry -> fields.put(entry.getKey(), entry.getValue()));
            output.append('{'); boolean first = true;
            for (var entry : fields.entrySet()) {
                if (!first) output.append(','); first = false;
                string(entry.getKey(), output); output.append(':'); append(entry.getValue(), output);
            }
            output.append('}'); return;
        }
        if (node.isArray()) {
            output.append('['); boolean first = true;
            for (JsonNode item : node) { if (!first) output.append(','); first = false; append(item, output); }
            output.append(']'); return;
        }
        if (node.isTextual()) { string(node.textValue(), output); return; }
        if (node.isFloatingPointNumber()) { output.append(pythonFloat(node.doubleValue())); return; }
        if (node.isIntegralNumber() || node.isBoolean()) { output.append(node); return; }
        throw failure("INVALID_JSON");
    }
    private static void string(String value, StringBuilder output) throws IOException {
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            if (Character.isHighSurrogate(character)) {
                if (++index >= value.length() || !Character.isLowSurrogate(value.charAt(index))) throw failure("INVALID_JSON");
            } else if (Character.isLowSurrogate(character)) throw failure("INVALID_JSON");
        }
        output.append('"');
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '"' -> output.append("\\\"");
                case '\\' -> output.append("\\\\");
                case '\b' -> output.append("\\b");
                case '\f' -> output.append("\\f");
                case '\n' -> output.append("\\n");
                case '\r' -> output.append("\\r");
                case '\t' -> output.append("\\t");
                default -> {
                    if (character < 32) output.append(String.format(java.util.Locale.ROOT, "\\u%04x", (int) character));
                    else output.append(character);
                }
            }
        }
        output.append('"');
    }
    /** CPython repr uses shortest round-tripping decimal, then -4/16 exponent thresholds. */
    private static String pythonFloat(double value) throws IOException {
        if (!Double.isFinite(value)) throw failure("INVALID_JSON");
        if (value == 0.0) return Double.doubleToRawLongBits(value) < 0 ? "-0.0" : "0.0";
        java.math.BigDecimal exact = new java.math.BigDecimal(value), shortest = exact;
        for (int precision = 1; precision <= 17; precision++) {
            var rounded = exact.round(new java.math.MathContext(precision, java.math.RoundingMode.HALF_EVEN));
            if (Double.doubleToLongBits(rounded.doubleValue()) == Double.doubleToLongBits(value)) { shortest = rounded.stripTrailingZeros(); break; }
        }
        int exponent = shortest.precision() - shortest.scale() - 1;
        if (exponent >= -4 && exponent < 16) {
            String plain = shortest.toPlainString(); return plain.contains(".") ? plain : plain + ".0";
        }
        String mantissa = shortest.movePointLeft(exponent).toPlainString();
        return mantissa + "e" + (exponent >= 0 ? "+" : "-") + String.format(java.util.Locale.ROOT, "%02d", Math.abs(exponent));
    }
    static String hash(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    static String digest(byte[] bytes) { return "sha256:" + hash(bytes); }
    static IOException failure(String code) { return new IOException(code); }
    static String text(JsonNode node, String field) throws IOException {
        JsonNode value = node.get(field);
        if (value == null || !value.isTextual() || value.textValue().isEmpty()) throw failure("PUBLICATION_FIELD_TYPE_INVALID");
        return value.textValue();
    }
}
