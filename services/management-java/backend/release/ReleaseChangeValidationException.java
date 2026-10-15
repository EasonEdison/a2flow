package dev.a2flow.management.release;

/** Deterministic rejection before createChange constructs or persists a new change. */
public final class ReleaseChangeValidationException extends IllegalArgumentException {
    private static final long serialVersionUID = 1L;

    private ReleaseChangeValidationException() {
        super("active release change already exists");
    }

    public static ReleaseChangeValidationException activeChangeExists() {
        return new ReleaseChangeValidationException();
    }

    public String getErrorCode() {
        return "RELEASE_ACTIVE_CHANGE_EXISTS";
    }
}
