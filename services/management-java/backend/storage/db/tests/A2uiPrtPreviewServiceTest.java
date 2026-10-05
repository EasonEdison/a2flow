package dev.a2flow.management.a2ui.preview;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import com.google.protobuf.ByteString;

import dev.a2flow.management.a2ui.runtime.proto.A2uiExecutionGrpc;
import dev.a2flow.management.a2ui.runtime.proto.ActRequest;
import dev.a2flow.management.a2ui.runtime.proto.ActivateRequest;
import dev.a2flow.management.a2ui.runtime.proto.ApplicationRelease;
import dev.a2flow.management.a2ui.runtime.proto.CatalogDescriptor;
import dev.a2flow.management.a2ui.runtime.proto.RuntimeResponse;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.capabilityrpc.GrpcTargetRegistry;
import dev.a2flow.management.capabilityrpc.proto.Environment;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import io.grpc.stub.StreamObserver;

/** Process-local PRT preview identity and idempotency behavior against a real loopback gRPC server. */
public final class A2uiPrtPreviewServiceTest {
    public static void main(String[] args) throws Exception {
        AtomicInteger activates = new AtomicInteger();
        AtomicInteger actions = new AtomicInteger();
        long[] observedUserId = new long[1];
        Server server = NettyServerBuilder.forPort(0).addService(new A2uiExecutionGrpc.A2uiExecutionImplBase() {
            @Override
            public void activate(ActivateRequest request, StreamObserver<RuntimeResponse> observer) {
                activates.incrementAndGet();
                observedUserId[0] = request.getContext().getUserId();
                observer.onNext(response());
                observer.onCompleted();
            }

            @Override
            public void act(ActRequest request, StreamObserver<RuntimeResponse> observer) {
                actions.incrementAndGet();
                check(request.getCard().getUserId() == Long.MAX_VALUE, "trusted card lost int64 userId");
                observer.onNext(response());
                observer.onCompleted();
            }
        }).build().start();
        try (GrpcTargetRegistry targets = new GrpcTargetRegistry(Map.of(
                A2uiPrtPreviewService.TARGET_KEY,
                Map.of(ReleaseEnvironment.PRT, new GrpcTargetRegistry.Endpoint(
                        "127.0.0.1", server.getPort(), true, null, null, null))))) {
            var repository = new SkillFactoryComponentAssetRepository() {
                @Override public ComponentAsset get(Long id) {
                    return id == 23L ? new ComponentAsset().setId(id)
                            .setAssetType("A2UI_APPLICATION").setComponentName("people-selector") : null;
                }
            };
            var admin = new AssetAuthorizationService() {
                @Override public boolean isAdmin(String operator) { return "9001".equals(operator); }
            };
            var service = new A2uiPrtPreviewService(admin, repository, targets);
            Map<String, String> start = Map.of("id", "23", "targetUserId",
                    Long.toString(Long.MAX_VALUE), "paramsJson", "{}", "requestId", "start-1");
            Map<String, Object> first = service.start("9001", start);
            service.start("9001", start);
            check(activates.get() == 1, "duplicate start dispatched twice");
            check(observedUserId[0] == Long.MAX_VALUE, "signed int64 userId lost precision");
            mustReject(() -> service.start("visitor", start), "A2UI_PRT_PREVIEW_ADMIN_REQUIRED");
            mustReject(() -> service.start("9001", Map.of("id", "23", "targetUserId", "9223372036854775808",
                    "paramsJson", "{}", "requestId", "start-overflow")),
                    "A2UI_PRT_PREVIEW_TARGET_USER_ID_INVALID");
            String sessionId = first.get("sessionId").toString();
            Map<String, String> action = Map.of("sessionId", sessionId, "actionName", "selectPage",
                    "surfaceId", "people", "sourceComponentId", "next", "contextJson", "{}",
                    "requestId", "action-1", "confirmed", "true");
            service.action("9001", action);
            service.action("9001", action);
            check(actions.get() == 1, "duplicate action dispatched twice");
            System.out.println("A2UI_PRT_PREVIEW_PASS: ADMIN gate, signed int64 identity, start/action idempotency");
        } finally {
            server.shutdownNow();
        }
    }

    private static RuntimeResponse response() {
        return RuntimeResponse.newBuilder()
                .setRelease(ApplicationRelease.newBuilder().setAppCode("people-selector")
                        .setSourceId("source-1").setDigest("digest-1").setAppBuildId("build-1")
                        .setEnvironment(Environment.PRT))
                .setCatalog(CatalogDescriptor.newBuilder().setProtocolVersion("v0.9.1")
                        .setCatalogId("a2flow.digital-employee.pc.v1")
                        .setCatalogRevision("1").setCatalogDigest("catalog-digest"))
                .setParamsJson(ByteString.copyFromUtf8("{}"))
                .setSnapshotJson(ByteString.copyFromUtf8("[]"))
                .setBusinessSuccess(true)
                .build();
    }

    private static void mustReject(Runnable operation, String code) {
        try {
            operation.run();
        } catch (A2uiPrtPreviewException expected) {
            check(code.equals(expected.getErrorCode()), "wrong rejection: " + expected.getErrorCode());
            return;
        }
        throw new AssertionError("expected rejection: " + code);
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
