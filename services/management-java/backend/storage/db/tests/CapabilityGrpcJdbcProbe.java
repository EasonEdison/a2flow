package dev.a2flow.management.capabilityrpc;

import java.lang.reflect.Field;
import java.sql.Connection;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import com.google.protobuf.*;
import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import dev.a2flow.management.agentcore.runtime.tool.*;
import dev.a2flow.management.capabilityrpc.proto.*;
import dev.a2flow.management.model.*;
import dev.a2flow.management.release.*;
import dev.a2flow.management.release.ReleaseModels.*;
import dev.a2flow.management.release.dependency.*;
import dev.a2flow.management.storage.db.mapper.AssetReleaseStateMapper;
import dev.a2flow.management.storage.db.migration.ExplicitManagementMigration;
import dev.a2flow.management.storage.db.repository.*;
import dev.a2flow.management.support.JsonSupport;
import io.grpc.*;
import io.grpc.protobuf.ProtoUtils;
import io.grpc.stub.ServerCalls;
import org.mybatis.spring.SqlSessionTemplate;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.jdbc.core.JdbcTemplate;

/** Real loopback gRPC -> PostgreSQL published resolver -> real protobuf downstream gRPC. */
public final class CapabilityGrpcJdbcProbe {
    private static final String ASSET = "probe-draft";
    private static final AtomicInteger CALLS = new AtomicInteger();
    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !args[0].matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/capability_rpc_test")) {
            throw new IllegalArgumentException("Disposable loopback capability_rpc_test required");
        }
        PGSimpleDataSource ds = new PGSimpleDataSource(); ds.setURL(args[0]); ds.setUser(args[1]);
        try (Connection connection = ds.getConnection()) { ExplicitManagementMigration.apply(connection); }
        var jdbc = new JdbcTemplate(ds);
        var file = descriptor();
        var set = DescriptorProtos.FileDescriptorSet.newBuilder().addFile(Capability.getDescriptor().toProto())
                .addFile(file.toProto()).build();
        String descriptor = Base64.getEncoder().encodeToString(set.toByteArray());
        var method = GrpcCapabilityContract.method(descriptor, "probe.Business", "Invoke", "context");
        var rpcMethod = MethodDescriptor.<DynamicMessage, DynamicMessage>newBuilder().setType(MethodDescriptor.MethodType.UNARY)
                .setFullMethodName("probe.Business/Invoke")
                .setRequestMarshaller(ProtoUtils.marshaller(DynamicMessage.getDefaultInstance(method.getInputType())))
                .setResponseMarshaller(ProtoUtils.marshaller(DynamicMessage.getDefaultInstance(method.getOutputType()))).build();
        var downstream = ServerServiceDefinition.builder("probe.Business").addMethod(rpcMethod,
                ServerCalls.asyncUnaryCall((request, observer) -> {
                    CALLS.incrementAndGet();
                    var authority = (DynamicMessage) request.getField(method.getInputType().findFieldByName("context"));
                    try {
                        var context = ExecutionContext.parseFrom(authority.toByteArray());
                        check(context.hasUserId() && context.getUserId() == Long.MIN_VALUE, "signed64 authority lost");
                        check(context.getEnvironment() == Environment.PRT && context.getRequestId().equals("probe-request"), "authority changed");
                        long quantity = (Long) request.getField(method.getInputType().findFieldByName("quantity"));
                        if (quantity == 7) Thread.sleep(200);
                        observer.onNext(DynamicMessage.newBuilder(method.getOutputType())
                                .setField(method.getOutputType().findFieldByName("quantity"), quantity).build());
                        observer.onCompleted();
                    } catch (Exception failure) { observer.onError(Status.INTERNAL.asRuntimeException()); }
                })).build();
        Server business = TrustedGrpcServer.start("127.0.0.1", 0, true, null, null, null, List.of(() -> downstream));
        try (var targets = new GrpcTargetRegistry(Map.of("business", Map.of(ReleaseEnvironment.PRT,
                new GrpcTargetRegistry.Endpoint("127.0.0.1", business.getPort(), true, null, null, null))))) {
            var executor = new CapabilityActionExecutor(new GrpcCapabilityTransport(targets));
            var configuration = new MybatisConfiguration(); configuration.setMapUnderscoreToCamelCase(true);
            configuration.addMapper(AssetReleaseStateMapper.class);
            var factory = new MybatisSqlSessionFactoryBean(); factory.setDataSource(ds); factory.setConfiguration(configuration);
            var mapper = new SqlSessionTemplate(factory.getObject()).getMapper(AssetReleaseStateMapper.class);
            var records = new AssetReleaseRecordStore(); inject(records, "mapper", mapper);
            var repository = new AssetReleaseStateRepository(); inject(repository, "assetReleaseStateMapper", mapper); inject(repository, "recordStore", records);
            var payloads = new CapabilityReleasePayloadAdapter();
            var adapter = new CapabilityAssetDependencyAdapter(); inject(adapter, "capabilityReleasePayloadAdapter", payloads);
            var beans = new DefaultListableBeanFactory(); beans.registerSingleton("capability", adapter);
            var registry = new AssetDependencyAdapterRegistry(beans.getBeanProvider(AssetDependencyAdapter.class));
            var provider = new CapabilityActionToolProvider();
            inject(provider, "capabilityReleasePayloadAdapter", payloads); inject(provider, "capabilityActionExecutor", executor);
            inject(provider, "environmentAwareAssetResolver", new DefaultEnvironmentAwareAssetResolver(repository, registry));
            var catalog = new CapabilityCatalogQueryService(repository,
                    new DefaultEnvironmentAwareAssetResolver(repository, registry), payloads, provider);
            var execution = new PublishedCapabilityExecutionService(provider, executor, catalog);
            Server server = TrustedGrpcServer.start("127.0.0.1", 0, true, null, null, null, List.of(new CapabilityGrpcService(execution)));
            ManagedChannel engine = io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder.forAddress("127.0.0.1", server.getPort()).usePlaintext().build();
            try {
                var draft = draft(descriptor, "string", 1000);
                publish(jdbc, draft, "digest-1", true);
                var client = CapabilityExecutionGrpc.newBlockingStub(engine).withDeadlineAfter(5, java.util.concurrent.TimeUnit.SECONDS);
                var context = new CapabilityRpcContext(Long.MIN_VALUE, ReleaseEnvironment.PRT, "probe-request", "PC").toProto();
                var resolved = client.resolve(ResolveRequest.newBuilder().setAssetKey(ASSET).setContext(context).build());
                check(resolved.getSourceId().equals("build-1") && resolved.getSourceDigest().equals("digest-1"), "DB immutable source lost");
                var request = ExecuteRequest.newBuilder().setAssetKey(ASSET).setContext(context)
                        .setArgumentsJson(ByteString.copyFromUtf8("{\"quantity\":9223372036854775807}"));
                var result = client.execute(request.build());
                check(result.getSuccess() && result.getDataJson().toStringUtf8().contains("9223372036854775807"), "binary RPC integer/result failed: " + result);
                var actionResult = execution.executeActionCode("probe.invoke", "{\"quantity\":1}",
                        new CapabilityRpcContext(Long.MIN_VALUE, ReleaseEnvironment.PRT, "probe-request", "PC"));
                check(actionResult.isSuccess(), "Published actionCode -> distinct draftId lookup failed");
                int calls = CALLS.get();
                var rejected = client.execute(request.setArgumentsJson(ByteString.copyFromUtf8("{\"quantity\":1,\"context\":{\"userId\":1}}")).build());
                check(!rejected.getSuccess() && CALLS.get() == calls, "model authority overwrite accepted");
                expectStatus(() -> client.resolve(ResolveRequest.newBuilder().setAssetKey(ASSET).setContext(context.toBuilder().clearUserId()).build()), Status.Code.INVALID_ARGUMENT);
                publish(jdbc, draft(descriptor, "integer", 1000), "digest-2", true);
                var schemaFailure = client.execute(request.setArgumentsJson(ByteString.copyFromUtf8("{\"quantity\":1}")).build());
                check(!schemaFailure.getSuccess() && schemaFailure.getErrorCode().equals("RESPONSE_SCHEMA_INVALID"), "response schema not enforced");
                publish(jdbc, draft(descriptor, "string", 40), "digest-3", true);
                var timeout = client.execute(request.setArgumentsJson(ByteString.copyFromUtf8("{\"quantity\":7}")).build());
                check(!timeout.getSuccess() && timeout.getErrorCode().equals("TRANSPORT_TIMEOUT"), "deadline not enforced");
                publish(jdbc, draft, "digest-4", false);
                expectStatus(() -> client.resolve(ResolveRequest.newBuilder().setAssetKey(ASSET).setContext(context).build()), Status.Code.INVALID_ARGUMENT);
                System.out.println("PASS：真实双段gRPC/Protobuf、PG当前发布源解析、signed64身份/业务整数无损、模型越权拒绝、响应Schema、deadline、PRT禁止ONLINE回退");
            } finally { engine.shutdownNow(); server.shutdownNow(); server.awaitTermination(); }
        } finally { business.shutdownNow(); business.awaitTermination(); }
    }
    private static CapabilityActionDraft draft(String descriptor, String resultType, int timeout) {
        Map<String, Object> variant = new LinkedHashMap<>();
        variant.put("apiSource", Map.of("sourceType", "GRPC"));
        variant.put("modelContract", Map.of("description", "probe", "inputFields", List.of(Map.of("toolField", "quantity", "type", "integer", "source", "MODEL_INPUT", "required", true))));
        variant.put("executionBinding", Map.of("bindingType", "GRPC", "target", Map.of("targetKey", "business", "serviceName", "probe.Business", "methodName", "Invoke", "descriptorSetBase64", descriptor, "contextField", "context"), "requestMappingsJson", "{\"quantity\":\"quantity\"}", "contextMappingsJson", "{}", "timeoutMs", timeout));
        variant.put("resultContract", Map.of("technicalOutputSchema", "{\"type\":\"object\",\"properties\":{\"quantity\":{\"type\":\"" + resultType + "\"}},\"required\":[\"quantity\"]}"));
        return new CapabilityActionDraft().setDraftId(ASSET).setRevision(1).setStatus("EDITING")
                .setDraft(Map.of("basicInfo", Map.of("actionCode", "probe.invoke", "nameCn", "探针", "businessDomain", "test", "description", "合成探针"), "supportedClients", List.of("PC"), "clientVariants", Map.of("PC", variant), "governance", Map.of("sideEffectLevel", "WRITE", "approvalPolicy", "REQUEST")));
    }
    private static void publish(JdbcTemplate jdbc, CapabilityActionDraft draft, String digest, boolean prt) {
        var snapshot = new AssetSnapshot().setAssetType("CAPABILITY_ACTION").setAssetKey(ASSET).setDigest(digest).setPayloadJson(JsonSupport.toJSON(draft));
        var state = new AssetReleaseState().setAssetType("CAPABILITY_ACTION").setAssetKey(ASSET)
                .setBuilds(List.of(new ReleaseBuild().setBuildId("build-1").setStatus("SUCCEEDED").setTargetVersion(1).setSourceDigest(digest).setSnapshot(snapshot)))
                .setVersions(List.of(new ReleaseVersion().setVersionId("version-1").setVersion(1).setSourceDigest(digest).setSnapshot(snapshot)))
                .setEnvironments(Map.of(prt ? "PRT" : "ONLINE", new EnvironmentState().setEnvironment(prt ? "PRT" : "ONLINE")
                        .setSourceType(prt ? "BUILD" : "VERSION").setSourceId(prt ? "build-1" : "version-1").setVersion(1).setDigest(digest)));
        jdbc.update("INSERT INTO skill_asset_release_state(asset_type,asset_key,revision,state_json) VALUES('CAPABILITY_ACTION',?,1,?) ON CONFLICT(asset_type,asset_key) DO UPDATE SET state_json=excluded.state_json", ASSET, JsonSupport.toJSON(state));
    }
    private static Descriptors.FileDescriptor descriptor() throws Exception {
        var request = DescriptorProtos.DescriptorProto.newBuilder().setName("Request")
                .addField(field("context", 1, DescriptorProtos.FieldDescriptorProto.Type.TYPE_MESSAGE).setTypeName(".a2flow.capability.v1.ExecutionContext"))
                .addField(field("quantity", 2, DescriptorProtos.FieldDescriptorProto.Type.TYPE_INT64));
        var response = DescriptorProtos.DescriptorProto.newBuilder().setName("Response").addField(field("quantity", 1, DescriptorProtos.FieldDescriptorProto.Type.TYPE_INT64));
        var file = DescriptorProtos.FileDescriptorProto.newBuilder().setName("probe.proto").setPackage("probe").setSyntax("proto3")
                .addDependency(Capability.getDescriptor().getName()).addMessageType(request).addMessageType(response)
                .addService(DescriptorProtos.ServiceDescriptorProto.newBuilder().setName("Business")
                        .addMethod(DescriptorProtos.MethodDescriptorProto.newBuilder().setName("Invoke").setInputType(".probe.Request").setOutputType(".probe.Response"))).build();
        return Descriptors.FileDescriptor.buildFrom(file, new Descriptors.FileDescriptor[]{Capability.getDescriptor()});
    }
    private static DescriptorProtos.FieldDescriptorProto.Builder field(String name, int number, DescriptorProtos.FieldDescriptorProto.Type type) {
        return DescriptorProtos.FieldDescriptorProto.newBuilder().setName(name).setNumber(number).setType(type).setLabel(DescriptorProtos.FieldDescriptorProto.Label.LABEL_OPTIONAL);
    }
    private static void inject(Object target, String field, Object value) throws Exception { Field member = target.getClass().getDeclaredField(field); member.setAccessible(true); member.set(target, value); }
    private static void check(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
    private static void expectStatus(Runnable action, Status.Code expected) { try { action.run(); } catch (StatusRuntimeException e) { check(e.getStatus().getCode() == expected, e.toString()); return; } throw new AssertionError("Expected " + expected); }
}
