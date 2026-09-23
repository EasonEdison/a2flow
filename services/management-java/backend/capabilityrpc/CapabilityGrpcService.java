package dev.a2flow.management.capabilityrpc;

import com.google.protobuf.ByteString;
import dev.a2flow.management.capabilityrpc.proto.*;
import dev.a2flow.management.support.JsonSupport;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.stub.StreamObserver;

/** Bind only using TrustedGrpcServer, never expose an unauthenticated remote listener. */
public final class CapabilityGrpcService extends CapabilityExecutionGrpc.CapabilityExecutionImplBase {
    private final PublishedCapabilityExecutionService service;
    public CapabilityGrpcService(PublishedCapabilityExecutionService service) { this.service = service; }
    @Override public void resolve(ResolveRequest request, StreamObserver<ResolveResponse> observer) {
        try {
            var context = CapabilityRpcContext.fromProto(request.getContext());
            if ("COMMON".equals(context.client())) throw new IllegalArgumentException("Runtime client must be PC/APP");
            var plan = service.resolve(request.getAssetKey(), context);
            observer.onNext(ResolveResponse.newBuilder().setAssetKey(request.getAssetKey()).setActionCode(plan.getActionCode())
                    .setCapabilityVersion(plan.getCapabilityVersion()).setDescription(empty(plan.getToolDescription()))
                    .setInputSchemaJson(plan.getInputSchema()).setKeyOutputFieldsJson(JsonSupport.toJSON(plan.getKeyOutputFields()))
                    .setResolvedEnvironment(Environment.valueOf(plan.getResolvedEnvironment().name()))
                    .setSourceId(plan.getSourceId()).setSourceDigest(plan.getSourceDigest()).build());
            observer.onCompleted();
        } catch (Exception e) { fail(observer, e); }
    }
    @Override public void execute(ExecuteRequest request, StreamObserver<ExecuteResponse> observer) {
        try {
            var context = CapabilityRpcContext.fromProto(request.getContext());
            if ("COMMON".equals(context.client())) throw new IllegalArgumentException("Runtime client must be PC/APP");
            if (!request.getArgumentsJson().isValidUtf8() || request.getArgumentsJson().size() > 1024 * 1024) {
                throw new IllegalArgumentException("UTF8 arguments limited to 1MiB");
            }
            var result = service.executePinned(request.getAssetKey(), request.getArgumentsJson().toStringUtf8(), context,
                    request.getExpectedSourceId(), request.getExpectedSourceDigest());
            observer.onNext(ExecuteResponse.newBuilder().setSuccess(result.isSuccess()).setActionCode(empty(result.getActionCode()))
                    .setCapabilityVersion(result.getCapabilityVersion()).setResolvedEnvironment(context.toProto().getEnvironment())
                    .setDataJson(ByteString.copyFromUtf8(JsonSupport.toJSON(result.getData())))
                    .setErrorCode(result.getErrorCode() == null ? "" : result.getErrorCode().name())
                    .setMessage(empty(result.getMessage())).setRequestId(context.requestId())
                    .setSourceId(request.getExpectedSourceId()).setSourceDigest(request.getExpectedSourceDigest()).build());
            observer.onCompleted();
        } catch (Exception e) { fail(observer, e); }
    }
    private static String empty(String value) { return value == null ? "" : value; }
    private static void fail(StreamObserver<?> observer, Exception e) {
        if (e instanceof StatusRuntimeException status) observer.onError(status);
        else if (e instanceof dev.a2flow.management.release.dependency.AssetDependencyResolutionException) {
            observer.onError(Status.FAILED_PRECONDITION.withDescription("CAPABILITY_RELEASE_NOT_AVAILABLE").asRuntimeException());
        }
        else if (e instanceof IllegalArgumentException) observer.onError(Status.INVALID_ARGUMENT.withDescription("Invalid capability request or published contract").asRuntimeException());
        else observer.onError(Status.INTERNAL.withDescription("Capability execution failed").asRuntimeException());
    }
}
