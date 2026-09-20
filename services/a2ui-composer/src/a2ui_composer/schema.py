"""Bounded JSON-schema admission and runtime data validation for A2UI."""

from a2flow_management import ManagementError


_COMMON = frozenset({"type", "enum", "const", "description", "title"})
_BY_TYPE = {
    "object": frozenset({"properties", "required", "additionalProperties"}),
    "array": frozenset({"items", "minItems", "maxItems", "uniqueItems"}),
    "string": frozenset({"minLength", "maxLength"}),
    "integer": frozenset({"minimum", "maximum"}),
    "number": frozenset({"minimum", "maximum"}),
    "boolean": frozenset(),
    "null": frozenset(),
}
_MAX_SCHEMA_NODES = 256
_MAX_SCHEMA_DEPTH = 8


def validate_input_schema(schema):
    """Admit only a small, closed JSON-schema profile safe for authored UI data."""
    count = [0]

    def visit(node, depth):
        count[0] += 1
        if (type(node) is not dict or depth > _MAX_SCHEMA_DEPTH
                or count[0] > _MAX_SCHEMA_NODES):
            raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
        kind = node.get("type")
        if kind not in _BY_TYPE or set(node) - (_COMMON | _BY_TYPE[kind]):
            raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
        if "description" in node and (
                type(node["description"]) is not str
                or len(node["description"]) > 2000):
            raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
        if "title" in node and (
                type(node["title"]) is not str or len(node["title"]) > 200):
            raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
        if "enum" in node and (
                type(node["enum"]) is not list or not node["enum"]
                or len(node["enum"]) > 64):
            raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
        if kind == "object":
            properties = node.get("properties")
            required = node.get("required")
            if (node.get("additionalProperties") is not False
                    or type(properties) is not dict or len(properties) > 64
                    or type(required) is not list
                    or len(required) != len(set(required))
                    or any(type(name) is not str or not name
                           or len(name) > 128 for name in properties)
                    or any(type(name) is not str or name not in properties
                           for name in required)):
                raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
            for child in properties.values():
                visit(child, depth + 1)
        elif kind == "array":
            if "items" not in node:
                raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
            for field in ("minItems", "maxItems"):
                if field in node and (
                        type(node[field]) is not int or node[field] < 0
                        or node[field] > 1024):
                    raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
            if ("minItems" in node and "maxItems" in node
                    and node["minItems"] > node["maxItems"]):
                raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
            if "uniqueItems" in node and type(node["uniqueItems"]) is not bool:
                raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
            visit(node["items"], depth + 1)
        elif kind == "string":
            _bounded_range(node, "minLength", "maxLength", 20000)
        elif kind in {"integer", "number"}:
            for field in ("minimum", "maximum"):
                if field in node and (type(node[field]) not in {int, float}
                                      or type(node[field]) is bool):
                    raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
            if ("minimum" in node and "maximum" in node
                    and node["minimum"] > node["maximum"]):
                raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")

    if type(schema) is not dict or schema.get("type") != "object":
        raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
    visit(schema, 0)
    return schema


def _bounded_range(node, lower, upper, maximum):
    for field in (lower, upper):
        if field in node and (
                type(node[field]) is not int or not 0 <= node[field] <= maximum):
            raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")
    if lower in node and upper in node and node[lower] > node[upper]:
        raise ManagementError("INVALID_APPLICATION_INPUT_SCHEMA")


def schema_path_exists(schema, path):
    """Return whether a JSON pointer names a declared node in the schema."""
    if path == "":
        return True
    if type(path) is not str or not path.startswith("/"):
        return False
    node = schema
    for raw in path[1:].split("/"):
        name = raw.replace("~1", "/").replace("~0", "~")
        kind = node.get("type") if type(node) is dict else None
        if kind == "object":
            node = node.get("properties", {}).get(name)
        elif kind == "array" and name.isdigit():
            node = node.get("items")
        else:
            return False
        if node is None:
            return False
    return True


def validate_json_data(schema, value):
    """Validate data with jsonschema after the bounded profile is admitted."""
    validate_input_schema(schema)
    try:
        from jsonschema import validators
    except ImportError:
        raise ManagementError("JSON_SCHEMA_VALIDATOR_REQUIRED") from None
    try:
        validator = validators.validator_for(schema)
        validator.check_schema(schema)
        return validator(schema).is_valid(value)
    except Exception:
        return False
