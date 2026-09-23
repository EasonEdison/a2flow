package dev.a2flow.management.access;

/** Exact identity conversion at JSON/protocol boundaries; internal identities remain Long. */
public final class UserIds {
    private UserIds() { }

    public static Long parseWire(String value) {
        if (value == null || !value.matches("0|-?[1-9][0-9]*")) {
            throw new IllegalArgumentException("userId must be a canonical signed decimal string");
        }
        try {
            return Long.valueOf(value);
        } catch (NumberFormatException failure) {
            throw new IllegalArgumentException("userId exceeds signed Long range", failure);
        }
    }

    public static String toWire(Long value) {
        if (value == null) {
            throw new IllegalArgumentException("A userId is required");
        }
        return value.toString();
    }
}
