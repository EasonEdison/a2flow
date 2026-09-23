package dev.a2flow.management.capabilityrpc;

import dev.a2flow.management.capabilityrpc.proto.*;
import dev.a2flow.management.a2ui.runtime.proto.A2uiExecutionGrpc;
import dev.a2flow.management.a2ui.runtime.proto.DescribeRequest;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;

/** Verify both real host routes exist and reject an absent immutable publication, never fake a success. */
public final class RuntimeGrpcHostProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !args[0].equals("18793")) throw new IllegalArgumentException("Isolated host port required");
        var channel = NettyChannelBuilder.forAddress("127.0.0.1", 18793).usePlaintext().build();
        try {
            var context = ExecutionContext.newBuilder().setUserId(0).setEnvironment(Environment.PRT)
                    .setRequestId("isolated-host-probe").setClient("PC").build();
            var capabilities = CapabilityExecutionGrpc.newBlockingStub(channel).withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS);
            expectPublishedRejection(() -> capabilities.resolve(ResolveRequest.newBuilder().setAssetKey("absent-probe").setContext(context).build()));
            var a2ui = A2uiExecutionGrpc.newBlockingStub(channel).withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS);
            expectPublishedRejection(() -> a2ui.describe(DescribeRequest.newBuilder().setAppCode("absent-probe").setContext(context).build()));
            System.out.println("PASS：真实ManagementApplication宿主注册Ability与A2UI两个gRPC服务，缺少发布均明确拒绝");
        } finally { channel.shutdownNow(); channel.awaitTermination(3, java.util.concurrent.TimeUnit.SECONDS); }
    }
    private static void expectPublishedRejection(Runnable call) {
        try { call.run(); } catch (StatusRuntimeException failure) {
            Status.Code code = failure.getStatus().getCode();
            if (code == Status.Code.INVALID_ARGUMENT || code == Status.Code.FAILED_PRECONDITION || code == Status.Code.NOT_FOUND) return;
            throw new AssertionError("Unexpected host result: " + code, failure);
        }
        throw new AssertionError("Absent published asset must not succeed");
    }
}
