package dev.a2flow.management.lifecycle;

/** Existing Runtime Skill identity contract. Never normalize or rename an asset implicitly. */
public final class SkillKeyValidator {
    public static final String PATTERN = "[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*";
    private SkillKeyValidator() { }
    public static boolean isValid(String value) {
        return value != null && !value.isEmpty() && value.length() <= 128 && value.matches(PATTERN);
    }
    public static void requireValid(String value) {
        if (!isValid(value)) throw SkillFactoryValidationException.invalidSkillKey();
    }
}
