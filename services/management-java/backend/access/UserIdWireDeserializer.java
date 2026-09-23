package dev.a2flow.management.access;

import java.io.IOException;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;

/** Rejects JSON numbers at the identity wire boundary before any coercion can lose precision. */
public final class UserIdWireDeserializer extends JsonDeserializer<String> {
    @Override
    public String deserialize(JsonParser parser, DeserializationContext context) throws IOException {
        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            return (String) context.handleUnexpectedToken(String.class, parser);
        }
        String value = parser.getText();
        try {
            UserIds.parseWire(value);
            return value;
        } catch (IllegalArgumentException failure) {
            return (String) context.handleWeirdStringValue(String.class, value, failure.getMessage());
        }
    }
}
