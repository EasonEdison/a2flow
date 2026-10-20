package dev.a2flow.management.capabilityrpc;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Objects;
import java.util.Set;
import org.springframework.stereotype.Component;
import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionExecutor.CapabilityExecutionException;
import dev.a2flow.management.capabilityrpc.proto.ApprovalReceipt;
import dev.a2flow.management.model.CapabilityActionExecutionPlan;
import dev.a2flow.management.model.CapabilityToolErrorCode;

/** Last admission before business RPC. Only host-supplied typed receipts are accepted. */
@Component
public final class CapabilityApprovalGuard {
    private final CapabilityApprovalStore store;
    public CapabilityApprovalGuard(CapabilityApprovalStore store) { this.store = store; }

    public static void validateGovernance(String sideEffect, String policy) {
        if (sideEffect == null || !Set.of("READ", "WRITE", "DESTRUCTIVE").contains(sideEffect)
                || policy == null || !Set.of("REQUEST_APPROVAL", "AUTO_EXECUTE").contains(policy)
                || (!"READ".equals(sideEffect) && !"REQUEST_APPROVAL".equals(policy))) {
            throw failure(CapabilityToolErrorCode.EXECUTION_PLAN_INVALID, "Unsupported capability governance");
        }
    }

    public void admit(CapabilityActionExecutionPlan plan, String argumentsJson,
            CapabilityRpcContext context, Object authority) {
        validateGovernance(plan.getSideEffectLevel(), plan.getApprovalPolicy());
        // Latest user policy: reads do not request or consume approval, even for old REQUEST_APPROVAL releases.
        if ("READ".equals(plan.getSideEffectLevel())) return;
        if (!(authority instanceof ApprovalReceipt receipt)) {
            throw failure(CapabilityToolErrorCode.APPROVAL_REQUIRED, "Explicit confirmation required before business write");
        }
        if (!identifier(receipt.getReceiptId()) || !identifier(receipt.getConfirmationId())
                || !identifier(receipt.getRunId()) || !identifier(receipt.getToolCallId())
                || !receipt.hasUserId() || receipt.getUserId() != context.userId()
                || !receipt.getEnvironment().name().equals(context.environment().name())
                || !bound(receipt.getActionCode(), plan.getActionCode())
                || !bound(receipt.getSourceId(), plan.getSourceId())
                || !bound(receipt.getSourceDigest(), plan.getSourceDigest())
                || !bound(receipt.getSideEffectLevel(), plan.getSideEffectLevel())
                || !bound(receipt.getApprovalPolicy(), plan.getApprovalPolicy())
                || !receipt.getArgumentsDigest().equals(argumentsDigest(argumentsJson))) {
            throw failure(CapabilityToolErrorCode.APPROVAL_INVALID, "Confirmation does not match immutable execution");
        }
        final boolean consumed;
        try { consumed = store.consume(receipt); }
        catch (RuntimeException unavailable) {
            throw failure(CapabilityToolErrorCode.APPROVAL_STORE_UNAVAILABLE, "Confirmation store unavailable; business not dispatched");
        }
        if (!consumed) {
            throw failure(CapabilityToolErrorCode.APPROVAL_ALREADY_CONSUMED, "Confirmation already consumed; do not retry business execution");
        }
    }

    public static String argumentsDigest(String rawJson) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(Objects.requireNonNull(rawJson).getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    private static boolean identifier(String value) {
        return value != null && value.matches("[A-Za-z0-9_.:/-]{1,200}");
    }
    private static boolean bound(String actual, String expected) {
        return actual != null && !actual.isBlank() && actual.length() <= 200 && actual.equals(expected);
    }
    private static CapabilityExecutionException failure(CapabilityToolErrorCode code, String message) {
        return new CapabilityExecutionException(code, message);
    }
}
