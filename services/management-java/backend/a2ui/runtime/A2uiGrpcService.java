package dev.a2flow.management.a2ui.runtime;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;
import com.fasterxml.jackson.core.type.TypeReference;
import com.google.protobuf.ByteString;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiActionInvocation;
import dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiRuntimeSession;
import dev.a2flow.management.a2ui.runtime.proto.*;
import dev.a2flow.management.capabilityrpc.CapabilityRpcContext;
import dev.a2flow.management.capabilityrpc.proto.ExecutionContext;
import dev.a2flow.management.capabilityrpc.proto.Environment;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.support.JsonSupport;

/** 必须由服务端共享认证拦截器保护；不对浏览器开放可信卡片入口。 */
@Service
public final class A2uiGrpcService extends A2uiExecutionGrpc.A2uiExecutionImplBase {
    private static final TypeReference<Map<String, Object>> OBJECT = new TypeReference<>() { };
    private static final TypeReference<List<Map<String, Object>>> MESSAGES = new TypeReference<>() { };
    private final A2uiRuntimeFacade facade;
    public A2uiGrpcService(A2uiRuntimeFacade facade) { this.facade = facade; }

    @Override
    public void describe(DescribeRequest request, StreamObserver<DescribeResponse> observer) {
        respond(observer, () -> {
            var result = facade.describe(context(request.getContext()), request.getAppCode());
            var response = DescribeResponse.newBuilder().setRelease(release(result.release()))
                    .setParamsSchemaJson(json(result.paramsSchema())).setInteractionMode(result.interactionMode())
                    .setCatalog(catalog(result.catalog()));
            result.actions().forEach(action -> response.addActions(action(action)));
            return response.build();
        });
    }

    @Override
    public void activate(ActivateRequest request, StreamObserver<RuntimeResponse> observer) {
        respond(observer, () -> response(facade.activate(context(request.getContext()),
                new A2uiRuntimeContracts.ActivateRequest(request.getAppCode(),
                        read(request.getParamsJson(), OBJECT)))));
    }

    @Override
    public void act(ActRequest request, StreamObserver<RuntimeResponse> observer) {
        respond(observer, () -> {
            var card = request.getCard();
            if (!card.hasUserId() || card.getAppCode().isBlank()) {
                throw new A2uiRuntimeContracts.RuntimeFailure("A2UI_CARD_CONTEXT_MISMATCH");
            }
            var trusted = new A2uiRuntimeContracts.TrustedCard(card.getUserId(),
                    card.getAppCode(), read(card.getParamsJson(), OBJECT), read(card.getSnapshotJson(), MESSAGES));
            var invocation = new A2uiActionInvocation(request.getCorrelationId(), request.getIdempotencyKey(),
                    read(request.getActionMessageJson(), OBJECT));
            return response(facade.act(context(request.getContext()),
                    new A2uiRuntimeContracts.ActionRequest(trusted, invocation)));
        });
    }

    private RuntimeResponse response(A2uiRuntimeContracts.RuntimeResult result) {
        var response = RuntimeResponse.newBuilder().setRelease(release(result.release()))
                .setParamsJson(json(result.params())).setMessagesJson(json(result.messages()))
                .setSnapshotJson(json(result.snapshot())).setCompleteInteraction(result.completeInteraction())
                .setSelectedBranchId(orEmpty(result.selectedBranchId())).setCatalog(catalog(result.catalog()))
                .setInteractionMode(result.interactionMode()).setBusinessSuccess(result.businessSuccess())
                .setSession(RuntimeSession.newBuilder().setToken(result.session().getRuntimeSessionToken())
                        .setAppBuildId(result.session().getAppBuildId()).setProtocolVersion(result.session().getProtocolVersion())
                        .setCatalogId(result.session().getCatalogId()).setCatalogRevision(result.session().getCatalogRevision())
                        .setCatalogDigest(result.session().getCatalogDigest()));
        result.actions().forEach(action -> response.addActions(action(action)));
        result.executions().forEach(value -> response.addExecutions(ExecutionSummary.newBuilder()
                .setBindingId(value.bindingId()).setActionCode(value.actionCode()).setSuccess(value.success())
                .setCapabilityVersion(value.capabilityVersion()).setErrorCode(orEmpty(value.errorCode()))));
        return response.build();
    }

    private ActionDescriptor action(A2uiRuntimeContracts.ActionDescriptor value) {
        return ActionDescriptor.newBuilder().setSurfaceId(value.surfaceId()).setComponentId(value.componentId())
                .setActionName(value.actionName()).setContextSchemaJson(json(value.contextSchema())).build();
    }

    private CatalogDescriptor catalog(A2uiRuntimeContracts.CatalogDescriptor value) {
        return CatalogDescriptor.newBuilder().setProtocolVersion(value.protocolVersion()).setCatalogId(value.catalogId())
                .setCatalogRevision(value.catalogRevision()).setCatalogDigest(value.catalogDigest()).build();
    }

    private ApplicationRelease release(A2uiRuntimeContracts.ReleaseIdentity value) {
        return ApplicationRelease.newBuilder().setAppCode(value.appCode()).setSourceId(value.sourceId())
                .setDigest(value.digest()).setAppBuildId(value.appBuildId())
                .setEnvironment(Environment.valueOf(value.environment().name())).build();
    }

    private CapabilityRpcContext context(ExecutionContext value) {
        if (!value.hasUserId()) { throw new A2uiRuntimeContracts.RuntimeFailure("A2UI_TRUSTED_CONTEXT_REQUIRED"); }
        return new CapabilityRpcContext(value.getUserId(), environment(value.getEnvironment()),
                value.getRequestId(), value.getClient());
    }

    private ReleaseEnvironment environment(Environment value) {
        return switch (value) {
            case PRT -> ReleaseEnvironment.PRT;
            case ONLINE -> ReleaseEnvironment.ONLINE;
            default -> throw new A2uiRuntimeContracts.RuntimeFailure("A2UI_ENVIRONMENT_REQUIRED");
        };
    }

    private <T> T read(ByteString value, TypeReference<T> type) {
        try {
            T result = JsonSupport.mapper().readValue(value.toByteArray(), type);
            if (result == null) { throw new IllegalArgumentException("null JSON"); }
            return result;
        } catch (IOException | IllegalArgumentException exception) {
            throw new A2uiRuntimeContracts.RuntimeFailure("A2UI_REQUEST_JSON_INVALID");
        }
    }

    private ByteString json(Object value) { return ByteString.copyFromUtf8(JsonSupport.toJSON(value)); }
    private String orEmpty(String value) { return value == null ? "" : value; }

    private <T> void respond(StreamObserver<T> observer, Supplier<T> operation) {
        try {
            observer.onNext(operation.get());
            observer.onCompleted();
        } catch (A2uiRuntimeContracts.RuntimeFailure exception) {
            observer.onError(Status.FAILED_PRECONDITION.withDescription(exception.getCode()).asRuntimeException());
        } catch (dev.a2flow.management.a2ui.runtime.show.A2uiApplicationShowRenderer.RenderException exception) {
            observer.onError(Status.FAILED_PRECONDITION.withDescription("A2UI_SHOW_" + exception.getCode()).asRuntimeException());
        } catch (dev.a2flow.management.a2ui.runtime.mapping.A2uiCapabilityRequestMapper.MappingException exception) {
            observer.onError(Status.FAILED_PRECONDITION.withDescription("A2UI_MAPPING_" + exception.getCode()).asRuntimeException());
        } catch (dev.a2flow.management.a2ui.runtime.adapter.A2uiResultAdapterEngine.AdapterException exception) {
            observer.onError(Status.FAILED_PRECONDITION.withDescription("A2UI_ADAPTER_" + exception.getCode()).asRuntimeException());
        } catch (dev.a2flow.management.a2ui.gateway.A2uiActionGatewayException exception) {
            observer.onError(Status.FAILED_PRECONDITION.withDescription(exception.getErrorCode()).asRuntimeException());
        } catch (IllegalArgumentException exception) {
            observer.onError(Status.INVALID_ARGUMENT.withDescription("A2UI_REQUEST_INVALID").asRuntimeException());
        } catch (RuntimeException exception) {
            // 不把业务原始响应、发布配置或异常 cause 传输/记录到日志。
            observer.onError(Status.INTERNAL.withDescription("A2UI_EXECUTION_FAILED").asRuntimeException());
        }
    }
}
