package dev.a2flow.management.capabilityrpc;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import com.google.protobuf.*;
import dev.a2flow.management.agentcore.runtime.engine.model.BaseAgentContext;
import dev.a2flow.management.agentcore.runtime.tool.*;
import dev.a2flow.management.capabilityrpc.proto.*;
import dev.a2flow.management.model.*;
import dev.a2flow.management.release.ReleaseEnvironment;
import io.grpc.*;
import io.grpc.protobuf.ProtoUtils;
import io.grpc.stub.ServerCalls;
import org.springframework.ai.chat.model.ToolContext;
import org.postgresql.ds.PGSimpleDataSource;

/** Synthetic loopback business RPC only. Optional PG mode requires a dedicated empty local probe DB. */
public final class CapabilityApprovalGuardProbe {
    private static final AtomicInteger CALLS = new AtomicInteger();
    private static int checks;
    private static final String JSON = "{\"quantity\":1}";
    public static void main(String[] args) throws Exception {
        var file = descriptor();
        var set = DescriptorProtos.FileDescriptorSet.newBuilder().addFile(Capability.getDescriptor().toProto())
                .addFile(file.toProto()).build();
        String descriptor = Base64.getEncoder().encodeToString(set.toByteArray());
        var method = GrpcCapabilityContract.method(descriptor, "approvalprobe.Business", "Invoke", "context");
        var rpcMethod = MethodDescriptor.<DynamicMessage, DynamicMessage>newBuilder().setType(MethodDescriptor.MethodType.UNARY)
                .setFullMethodName("approvalprobe.Business/Invoke")
                .setRequestMarshaller(ProtoUtils.marshaller(DynamicMessage.getDefaultInstance(method.getInputType())))
                .setResponseMarshaller(ProtoUtils.marshaller(DynamicMessage.getDefaultInstance(method.getOutputType()))).build();
        var service = ServerServiceDefinition.builder("approvalprobe.Business").addMethod(rpcMethod,
                ServerCalls.asyncUnaryCall((request, observer) -> {
                    CALLS.incrementAndGet();
                    observer.onNext(DynamicMessage.newBuilder(method.getOutputType())
                            .setField(method.getOutputType().findFieldByName("quantity"), 1L).build());
                    observer.onCompleted();
                })).build();
        Server business = TrustedGrpcServer.start("127.0.0.1", 0, true, null, null, null, List.of(() -> service));
        Set<String> consumed = ConcurrentHashMap.newKeySet();
        CapabilityApprovalStore memory = receipt -> consumed.add(receipt.getReceiptId());
        try (var targets = new GrpcTargetRegistry(Map.of("probe", Map.of(ReleaseEnvironment.PRT,
                new GrpcTargetRegistry.Endpoint("127.0.0.1", business.getPort(), true, null, null, null))))) {
            var transport = new GrpcCapabilityTransport(targets);
            var executor = new CapabilityActionExecutor(transport, new CapabilityApprovalGuard(memory));
            var read = plan(descriptor); var write = read.toBuilder().sideEffectLevel("WRITE").build();
            check(run(executor, read, JSON, null).isSuccess() && CALLS.get() == 1, "READ old REQUEST_APPROVAL must execute");
            check(run(executor, read.toBuilder().approvalPolicy("AUTO_EXECUTE").build(), JSON, null).isSuccess(), "READ AUTO_EXECUTE");
            var receipt = receipt(write, "confirm-1");
            check(run(executor, read, JSON, receipt).isSuccess() && consumed.isEmpty(), "READ ignores and does not consume receipt");
            rejected(executor, write, JSON, null, "APPROVAL_REQUIRED");
            for (String policy : Arrays.asList(null, "", "REQUEST", "AUTO_EXECUTE")) {
                rejected(executor, write.toBuilder().approvalPolicy(policy).build(), JSON, receipt, "EXECUTION_PLAN_INVALID");
            }
            for (String sideEffect : Arrays.asList(null, "", "UNKNOWN")) {
                rejected(executor, read.toBuilder().sideEffectLevel(sideEffect).build(), JSON, null, "EXECUTION_PLAN_INVALID");
            }
            rejected(executor, write, "{\"quantity\":1,\"reviewedDemoApproved\":true}", null, "ARGUMENT_INVALID");
            rejected(executor, write, "{\"quantity\":1,\"capabilityApprovalReceipt\":{}}", null, "ARGUMENT_INVALID");
            rejected(executor, write, JSON, Map.of("approved", true), "APPROVAL_REQUIRED");
            rejected(executor, write, JSON, receipt.toBuilder().setUserId(99).build(), "APPROVAL_INVALID");
            rejected(executor, write, JSON, receipt.toBuilder().setEnvironment(Environment.ONLINE).build(), "APPROVAL_INVALID");
            rejected(executor, write, JSON, receipt.toBuilder().setActionCode("other.action").build(), "APPROVAL_INVALID");
            rejected(executor, write, JSON, receipt.toBuilder().setSourceId("another-build").build(), "APPROVAL_INVALID");
            rejected(executor, write, JSON, receipt.toBuilder().setSourceDigest("new-version").build(), "APPROVAL_INVALID");
            rejected(executor, write, JSON, receipt.toBuilder().setSideEffectLevel("READ").build(), "APPROVAL_INVALID");
            rejected(executor, write, JSON, receipt.toBuilder().setApprovalPolicy("AUTO_EXECUTE").build(), "APPROVAL_INVALID");
            rejected(executor, write, JSON, receipt.toBuilder().clearConfirmationId().build(), "APPROVAL_INVALID");
            rejected(executor, write, JSON, receipt.toBuilder().clearRunId().build(), "APPROVAL_INVALID");
            rejected(executor, write, "{\"quantity\":2}", receipt, "APPROVAL_INVALID");
            check(consumed.isEmpty(), "Invalid requests must not consume");
            executor.preview(write, JSON, context(receipt), ReleaseEnvironment.PRT, ReleaseEnvironment.PRT);
            check(consumed.isEmpty(), "preview cannot consume");
            int before = CALLS.get();
            check(run(executor, write, JSON, receipt).isSuccess() && CALLS.get() == before + 1, "confirmed write dispatch exactly once in probe");
            rejected(executor, write, JSON, receipt, "APPROVAL_ALREADY_CONSUMED");
            var failedStore = new CapabilityActionExecutor(transport, new CapabilityApprovalGuard(value -> { throw new IllegalStateException(); }));
            rejected(failedStore, write, JSON, receipt(write, "confirm-2"), "APPROVAL_STORE_UNAVAILABLE");
            var destructive = write.toBuilder().sideEffectLevel("DESTRUCTIVE").build();
            rejected(executor, destructive, JSON, null, "APPROVAL_REQUIRED");
            check(run(executor, destructive, JSON, receipt(destructive, "confirm-3")).isSuccess(), "confirmed destructive");
            var stripped = TrustedToolContext.build(null, Map.of(TrustedToolContext.CAPABILITY_APPROVAL_RECEIPT, receipt,
                    TrustedToolContext.REVIEWED_DEMO_APPROVED, true));
            check(!stripped.containsKey(TrustedToolContext.CAPABILITY_APPROVAL_RECEIPT)
                    && !stripped.containsKey(TrustedToolContext.REVIEWED_DEMO_APPROVED), "ordinary context cannot confer approval");
            if (args.length != 0) postgres(args, write);
            System.out.println("{\"result\":\"PASS\",\"checks\":" + checks + ",\"businessRpcCalls\":" + CALLS.get()
                    + ",\"postgres\":" + (args.length != 0) + "}");
        } finally { business.shutdownNow(); business.awaitTermination(5, TimeUnit.SECONDS); }
    }
    private static void postgres(String[] args, CapabilityActionExecutionPlan plan) throws Exception {
        if (args.length != 2 || !args[0].matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/a2flow_approval_probe")) {
            throw new IllegalArgumentException("Use dedicated loopback jdbc:postgresql://127.0.0.1:PORT/a2flow_approval_probe USER; password via A2FLOW_PROBE_DB_PASSWORD");
        }
        var base = new PGSimpleDataSource(); base.setURL(args[0]); base.setUser(args[1]);
        base.setPassword(System.getenv("A2FLOW_PROBE_DB_PASSWORD"));
        String schema = "approval_probe_" + UUID.randomUUID().toString().replace("-", "");
        try (var connection = base.getConnection(); var sql = connection.createStatement()) {
            try (var tables = sql.executeQuery("SELECT count(*) FROM pg_tables WHERE schemaname='public'")) {
                tables.next(); check(tables.getInt(1) == 0, "Probe database public schema must be empty");
            }
            sql.execute("CREATE SCHEMA " + schema);
        }
        var ds = new PGSimpleDataSource(); ds.setURL(args[0]); ds.setUser(args[1]);
        ds.setPassword(System.getenv("A2FLOW_PROBE_DB_PASSWORD")); ds.setCurrentSchema(schema);
        try {
            try (var connection = ds.getConnection(); var sql = connection.createStatement();
                    var resource = CapabilityApprovalGuardProbe.class.getClassLoader().getResourceAsStream(
                            "storage/db/migration/V003__capability_approval_consumption.sql")) {
                check(resource != null, "Migration resource"); sql.execute(new String(resource.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8));
            }
            var receipt = receipt(plan, "pg-confirm");
            check(new PostgresCapabilityApprovalStore(ds).consume(receipt), "PG first consume");
            check(!new PostgresCapabilityApprovalStore(ds).consume(receipt), "New store cannot reconsume persisted approval");
            check(!new PostgresCapabilityApprovalStore(ds).consume(receipt.toBuilder().setReceiptId("alias").build()), "Confirmation alias cannot reconsume");
            check(!new PostgresCapabilityApprovalStore(ds).consume(receipt.toBuilder().setReceiptId("alias2").setConfirmationId("new-confirm").build()), "Same tool call cannot re-dispatch");
            var concurrent = receipt(plan, "pg-race");
            var pool = Executors.newFixedThreadPool(4);
            try {
                var futures = new ArrayList<Future<Boolean>>();
                for (int index = 0; index < 8; index++) futures.add(pool.submit(() -> new PostgresCapabilityApprovalStore(ds).consume(concurrent)));
                int winners = 0; for (var future : futures) if (future.get(10, TimeUnit.SECONDS)) winners++;
                check(winners == 1, "Concurrent approval has one winner");
            } finally { pool.shutdownNow(); }
            try (var connection = ds.getConnection(); var sql = connection.createStatement()) {
                sql.execute("CREATE FUNCTION reject_probe_approval() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic rollback'; END $$");
                sql.execute("CREATE TRIGGER reject_probe_approval BEFORE INSERT ON capability_approval_consumption FOR EACH ROW WHEN (NEW.receipt_id='pg-rollback') EXECUTE FUNCTION reject_probe_approval()");
            }
            boolean rejected = false;
            try { new PostgresCapabilityApprovalStore(ds).consume(receipt(plan, "pg-rollback")); }
            catch (IllegalStateException expected) { rejected = true; }
            check(rejected, "SQL failure must reject admission");
            try (var connection = ds.getConnection(); var sql = connection.createStatement();
                    var rows = sql.executeQuery("SELECT count(*) FROM capability_approval_consumption WHERE receipt_id='pg-rollback'")) {
                rows.next(); check(rows.getInt(1) == 0, "Failed claim transaction rolled back");
            }
        } finally {
            try (var connection = base.getConnection(); var sql = connection.createStatement()) {
                sql.execute("DROP SCHEMA " + schema + " CASCADE");
            }
        }
    }
    private static CapabilityToolResult run(CapabilityActionExecutor executor, CapabilityActionExecutionPlan plan, String json, Object receipt) {
        return executor.executeResult(plan, json, context(receipt), ReleaseEnvironment.PRT, ReleaseEnvironment.PRT);
    }
    private static ToolContext context(Object receipt) {
        var agent = new BaseAgentContext(); agent.setUserId(7L); agent.setClient("PC"); agent.setEnv("PRT");
        var values = new HashMap<String, Object>(); values.put("agentContext", agent); values.put(TrustedToolContext.TRACE_ID, "approval-probe");
        values.put(TrustedToolContext.REVIEWED_DEMO_APPROVED, true);
        if (receipt != null) values.put(TrustedToolContext.CAPABILITY_APPROVAL_RECEIPT, receipt);
        return new ToolContext(values);
    }
    private static ApprovalReceipt receipt(CapabilityActionExecutionPlan plan, String id) {
        return ApprovalReceipt.newBuilder().setReceiptId(id).setConfirmationId(id).setUserId(7).setEnvironment(Environment.PRT)
                .setRunId("probe-run").setToolCallId("tool:" + id).setActionCode(plan.getActionCode()).setSourceId(plan.getSourceId())
                .setSourceDigest(plan.getSourceDigest()).setArgumentsDigest(CapabilityApprovalGuard.argumentsDigest(JSON))
                .setSideEffectLevel(plan.getSideEffectLevel()).setApprovalPolicy(plan.getApprovalPolicy()).build();
    }
    private static void rejected(CapabilityActionExecutor executor, CapabilityActionExecutionPlan plan, String json, Object receipt, String code) {
        int before = CALLS.get(); var result = run(executor, plan, json, receipt);
        check(!result.isSuccess() && result.getErrorCode().name().equals(code) && CALLS.get() == before, "No-RPC rejection " + code);
    }
    private static void check(boolean condition, String message) { checks++; if (!condition) throw new AssertionError(message); }
    private static CapabilityActionExecutionPlan plan(String descriptor) {
        return CapabilityActionExecutionPlan.builder().actionCode("probe.write").sourceId("probe-build-1").sourceDigest("probe-source-digest")
                .capabilityVersion(1).resolvedEnvironment(ReleaseEnvironment.PRT).clientType("PC").contractClientType("PC")
                .bindingType("GRPC").sourceType("GRPC").sideEffectLevel("READ").approvalPolicy("REQUEST_APPROVAL")
                .targetKey("probe").serviceName("approvalprobe.Business").methodName("Invoke").contextField("context")
                .descriptorSetBase64(descriptor).timeoutMs(3000).maxResponseBytes(1024 * 1024)
                .technicalOutputSchema("{\"type\":\"object\",\"properties\":{\"quantity\":{\"type\":\"string\"}}}")
                .modelArgumentFields(List.of("quantity")).requiredArgumentFields(List.of("quantity"))
                .argumentTypes(Map.of("quantity", "integer")).argumentSchemas(Map.of()).allowedArgumentValues(Map.of())
                .requestMappings(Map.of("quantity", "quantity")).contextMappings(Map.of()).contextValueMappings(Map.of()).constantMappings(Map.of()).build();
    }
    private static Descriptors.FileDescriptor descriptor() throws Exception {
        var request = DescriptorProtos.DescriptorProto.newBuilder().setName("Request")
                .addField(field("context", 1, DescriptorProtos.FieldDescriptorProto.Type.TYPE_MESSAGE).setTypeName(".a2flow.capability.v1.ExecutionContext"))
                .addField(field("quantity", 2, DescriptorProtos.FieldDescriptorProto.Type.TYPE_INT64));
        var response = DescriptorProtos.DescriptorProto.newBuilder().setName("Response").addField(field("quantity", 1, DescriptorProtos.FieldDescriptorProto.Type.TYPE_INT64));
        var file = DescriptorProtos.FileDescriptorProto.newBuilder().setName("approval_probe.proto").setPackage("approvalprobe").setSyntax("proto3")
                .addDependency(Capability.getDescriptor().getName()).addMessageType(request).addMessageType(response)
                .addService(DescriptorProtos.ServiceDescriptorProto.newBuilder().setName("Business")
                        .addMethod(DescriptorProtos.MethodDescriptorProto.newBuilder().setName("Invoke").setInputType(".approvalprobe.Request").setOutputType(".approvalprobe.Response"))).build();
        return Descriptors.FileDescriptor.buildFrom(file, new Descriptors.FileDescriptor[]{Capability.getDescriptor()});
    }
    private static DescriptorProtos.FieldDescriptorProto.Builder field(String name, int number, DescriptorProtos.FieldDescriptorProto.Type type) {
        return DescriptorProtos.FieldDescriptorProto.newBuilder().setName(name).setNumber(number).setType(type).setLabel(DescriptorProtos.FieldDescriptorProto.Label.LABEL_OPTIONAL);
    }
}
