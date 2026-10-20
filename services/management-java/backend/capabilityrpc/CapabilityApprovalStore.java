package dev.a2flow.management.capabilityrpc;

import dev.a2flow.management.capabilityrpc.proto.ApprovalReceipt;

/** Durable admission, not a business retry log. False means already consumed. */
@FunctionalInterface
public interface CapabilityApprovalStore {
    boolean consume(ApprovalReceipt receipt);
}
