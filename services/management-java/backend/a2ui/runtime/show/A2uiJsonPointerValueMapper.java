package dev.a2flow.management.a2ui.runtime.show;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * A2UI Application Binding 使用的有界 JSON Pointer 值映射器。
 *
 * <p>上游 ShowInput、RequestMapping 和 ResultAdapter 都只提交发布态 JSON Pointer；本类在深拷贝
 * JSON 树上读取或写入，明确区分路径缺失与显式 null，并禁止数组空洞、非法转义和越界深度。
 * 下游拿到的是与输入对象隔离的普通 Map/List/Scalar。本类不读取身份上下文、不决定 required 语义，
 * 也不执行 Capability 或修改 RuntimeSurfaceLedger。</p>
 */
public class A2uiJsonPointerValueMapper {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final String ROOT_PATH = "/";
    private static final int MAX_POINTER_LENGTH = 1024;
    private static final int MAX_POINTER_DEPTH = 64;
    private static final int MAX_ARRAY_INDEX = 100_000;

    /** 读取路径；根路径使用空串或 {@code /}，返回值与原对象隔离。 */
    public LookupValue read(Object root, String pointer) {
        JsonNode current = OBJECT_MAPPER.valueToTree(root);
        if (isRoot(pointer)) {
            return LookupValue.found(toJavaValue(current));
        }
        List<String> tokens = tokens(pointer);
        for (String token : tokens) {
            if (current == null || current.isNull() || current.isMissingNode()) {
                return LookupValue.missing();
            }
            if (current.isObject()) {
                current = current.get(token);
            } else if (current.isArray()) {
                int index = parseArrayIndex(token);
                current = index < current.size() ? current.get(index) : null;
            } else {
                return LookupValue.missing();
            }
        }
        return current == null || current.isMissingNode()
                ? LookupValue.missing() : LookupValue.found(toJavaValue(current));
    }

    /**
     * 在深拷贝上设置路径并返回新根对象；写入数组时只允许覆盖现有元素或追加一个元素。
     */
    public Object write(Object root, String pointer, Object value) {
        if (isRoot(pointer)) {
            return deepCopy(value);
        }
        JsonNode mutableRoot = OBJECT_MAPPER.valueToTree(root);
        if (mutableRoot == null || !mutableRoot.isContainerNode()) {
            throw failure(Code.PATH_CONFLICT, pointer, "root must be an object or array");
        }
        List<String> tokens = tokens(pointer);
        JsonNode parent = mutableRoot;
        for (int index = 0; index < tokens.size() - 1; index++) {
            parent = childContainer(parent, tokens.get(index), tokens.get(index + 1), pointer);
        }
        setChild(parent, tokens.get(tokens.size() - 1),
                OBJECT_MAPPER.valueToTree(value), pointer);
        return toJavaValue(mutableRoot);
    }

    private JsonNode childContainer(JsonNode parent, String token,
            String nextToken, String pointer) {
        if (parent.isObject()) {
            ObjectNode object = (ObjectNode) parent;
            JsonNode child = object.get(token);
            if (child == null || child.isNull()) {
                child = isArrayIndex(nextToken)
                        ? JsonNodeFactory.instance.arrayNode()
                        : JsonNodeFactory.instance.objectNode();
                object.set(token, child);
            }
            if (!child.isContainerNode()) {
                throw failure(Code.PATH_CONFLICT, pointer,
                        "path crosses a scalar value");
            }
            return child;
        }
        if (parent.isArray()) {
            ArrayNode array = (ArrayNode) parent;
            int arrayIndex = parseArrayIndex(token);
            if (arrayIndex > array.size()) {
                throw failure(Code.ARRAY_GAP, pointer, "array path creates a gap");
            }
            if (arrayIndex == array.size()) {
                JsonNode child = isArrayIndex(nextToken)
                        ? JsonNodeFactory.instance.arrayNode()
                        : JsonNodeFactory.instance.objectNode();
                array.add(child);
                return child;
            }
            JsonNode child = array.get(arrayIndex);
            if (child == null || child.isNull()) {
                child = isArrayIndex(nextToken)
                        ? JsonNodeFactory.instance.arrayNode()
                        : JsonNodeFactory.instance.objectNode();
                array.set(arrayIndex, child);
            }
            if (!child.isContainerNode()) {
                throw failure(Code.PATH_CONFLICT, pointer,
                        "path crosses a scalar value");
            }
            return child;
        }
        throw failure(Code.PATH_CONFLICT, pointer, "path parent is not a container");
    }

    private void setChild(JsonNode parent, String token, JsonNode value, String pointer) {
        if (parent.isObject()) {
            ((ObjectNode) parent).set(token, value);
            return;
        }
        if (parent.isArray()) {
            ArrayNode array = (ArrayNode) parent;
            int arrayIndex = parseArrayIndex(token);
            if (arrayIndex > array.size()) {
                throw failure(Code.ARRAY_GAP, pointer, "array path creates a gap");
            }
            if (arrayIndex == array.size()) {
                array.add(value);
            } else {
                array.set(arrayIndex, value);
            }
            return;
        }
        throw failure(Code.PATH_CONFLICT, pointer, "path parent is not a container");
    }

    private List<String> tokens(String pointer) {
        if (pointer == null || pointer.length() > MAX_POINTER_LENGTH
                || !pointer.startsWith(ROOT_PATH) || isRoot(pointer)) {
            throw failure(Code.POINTER_INVALID, pointer, "invalid JSON Pointer");
        }
        String[] rawTokens = pointer.substring(1).split(ROOT_PATH, -1);
        if (rawTokens.length == 0 || rawTokens.length > MAX_POINTER_DEPTH) {
            throw failure(Code.POINTER_INVALID, pointer, "invalid JSON Pointer depth");
        }
        java.util.ArrayList<String> decoded = new java.util.ArrayList<>(rawTokens.length);
        for (String rawToken : rawTokens) {
            decoded.add(decodeToken(rawToken, pointer));
        }
        return decoded;
    }

    private String decodeToken(String token, String pointer) {
        StringBuilder decoded = new StringBuilder(token.length());
        for (int index = 0; index < token.length(); index++) {
            char current = token.charAt(index);
            if (current != '~') {
                decoded.append(current);
                continue;
            }
            if (index + 1 >= token.length()) {
                throw failure(Code.POINTER_INVALID, pointer, "invalid JSON Pointer escape");
            }
            char escaped = token.charAt(++index);
            if (escaped == '0') {
                decoded.append('~');
            } else if (escaped == '1') {
                decoded.append('/');
            } else {
                throw failure(Code.POINTER_INVALID, pointer, "invalid JSON Pointer escape");
            }
        }
        return decoded.toString();
    }

    private boolean isRoot(String pointer) {
        return pointer != null && (pointer.isEmpty() || ROOT_PATH.equals(pointer));
    }

    private boolean isArrayIndex(String token) {
        try {
            parseArrayIndex(token);
            return true;
        } catch (MappingException exception) {
            return false;
        }
    }

    private int parseArrayIndex(String token) {
        if (token == null || token.isEmpty() || token.length() > 1 && token.charAt(0) == '0') {
            throw failure(Code.POINTER_INVALID, token, "invalid array index");
        }
        try {
            int index = Integer.parseInt(token);
            if (index < 0 || index > MAX_ARRAY_INDEX) {
                throw failure(Code.POINTER_INVALID, token, "array index exceeds limit");
            }
            return index;
        } catch (NumberFormatException exception) {
            throw failure(Code.POINTER_INVALID, token, "invalid array index");
        }
    }

    private Object deepCopy(Object value) {
        return toJavaValue(OBJECT_MAPPER.valueToTree(value));
    }

    private Object toJavaValue(JsonNode value) {
        return value == null || value.isMissingNode()
                ? null : OBJECT_MAPPER.convertValue(value, Object.class);
    }

    private MappingException failure(Code code, String pointer, String reason) {
        return new MappingException(code, pointer, reason);
    }

    public enum Code {
        POINTER_INVALID,
        PATH_CONFLICT,
        ARRAY_GAP
    }

    /** JSON Pointer 结构或目标树冲突；不携带原始业务值。 */
    public static class MappingException extends IllegalArgumentException {
        private final Code code;
        private final String pointer;

        MappingException(Code code, String pointer, String reason) {
            super(reason);
            this.code = code;
            this.pointer = pointer;
        }

        public Code getCode() {
            return code;
        }

        public String getPointer() {
            return pointer;
        }
    }

    /** 路径读取结果；found=true 时 value 仍可能是显式 null。 */
    public static final class LookupValue {
        private final boolean found;
        private final Object value;

        private LookupValue(boolean found, Object value) {
            this.found = found;
            this.value = value;
        }

        static LookupValue found(Object value) {
            return new LookupValue(true, value);
        }

        static LookupValue missing() {
            return new LookupValue(false, null);
        }

        public boolean isFound() {
            return found;
        }

        public Object getValue() {
            return value;
        }
    }
}
