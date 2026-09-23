package dev.a2flow.management.capabilityrpc;

import java.util.Map;
import java.util.concurrent.TimeUnit;
import com.google.protobuf.DynamicMessage;
import com.google.protobuf.util.JsonFormat;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;
import io.grpc.CallOptions;
import io.grpc.MethodDescriptor;
import io.grpc.protobuf.ProtoUtils;
import io.grpc.stub.ClientCalls;
import dev.a2flow.management.model.CapabilityActionExecutionPlan;
import dev.a2flow.management.model.CapabilityToolErrorCode;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionExecutor.CapabilityExecutionException;

/** Real unary protobuf RPC using the immutable, registered method descriptor. No HTTP transport. */
public final class GrpcCapabilityTransport {
    private final GrpcTargetRegistry targets;
    public GrpcCapabilityTransport(GrpcTargetRegistry targets) { this.targets = targets; }

    public Object execute(CapabilityActionExecutionPlan plan, Map<String, Object> business,
            CapabilityRpcContext context) throws Exception {
        var method = GrpcCapabilityContract.method(plan.getDescriptorSetBase64(), plan.getServiceName(),
                plan.getMethodName(), plan.getContextField());
        var contextField = method.getInputType().findFieldByName(plan.getContextField());
        if (business.containsKey(contextField.getName()) || business.containsKey(contextField.getJsonName())) {
            throw new CapabilityExecutionException(CapabilityToolErrorCode.REQUEST_MAPPING_INVALID,
                    "Business mappings cannot write the reserved execution context");
        }
        DynamicMessage.Builder request = DynamicMessage.newBuilder(method.getInputType());
        // Strict parser rejects unknown fields and out-of-range protobuf integer values.
        JsonFormat.parser().merge(JsonSupport.toJSON(business), request);
        request.setField(contextField, DynamicMessage.parseFrom(contextField.getMessageType(), context.toProto().toByteArray()));
        var schemaNode = JsonSupport.mapper().readTree(plan.getTechnicalOutputSchema());
        rejectExternalSchema(schemaNode);
        var schema = SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_7).getSchema(schemaNode);
        var descriptor = MethodDescriptor.<DynamicMessage, DynamicMessage>newBuilder()
                .setType(MethodDescriptor.MethodType.UNARY)
                .setFullMethodName(MethodDescriptor.generateFullMethodName(plan.getServiceName(), plan.getMethodName()))
                .setRequestMarshaller(ProtoUtils.marshaller(DynamicMessage.getDefaultInstance(method.getInputType())))
                .setResponseMarshaller(ProtoUtils.marshaller(DynamicMessage.getDefaultInstance(method.getOutputType())))
                .build();
        if (request.build().getSerializedSize() > 1024 * 1024) throw new IllegalArgumentException("RPC request exceeds 1MiB");
        DynamicMessage response = ClientCalls.blockingUnaryCall(targets.channel(plan.getTargetKey(), context.environment()),
                descriptor, CallOptions.DEFAULT.withDeadlineAfter(plan.getTimeoutMs(), TimeUnit.MILLISECONDS)
                        .withMaxInboundMessageSize(plan.getMaxResponseBytes()), request.build());
        String json = JsonFormat.printer().includingDefaultValueFields().print(response);
        var resultNode = JsonSupport.mapper().readTree(json);
        if (!schema.validate(resultNode).isEmpty()) throw new CapabilityExecutionException(
                CapabilityToolErrorCode.RESPONSE_SCHEMA_INVALID, "RPC result does not match published technicalOutputSchema");
        return JsonSupport.fromJSON(json, Object.class);
    }
    private static void rejectExternalSchema(com.fasterxml.jackson.databind.JsonNode node) {
        if (node.isObject() && node.has("$ref") && !node.get("$ref").asText().startsWith("#")) {
            throw new IllegalArgumentException("External schema references forbidden");
        }
        if (node.has("$dynamicRef") || node.has("$recursiveRef") || (node.has("$schema")
                && !java.util.Set.of("http://json-schema.org/draft-07/schema#", "https://json-schema.org/draft-07/schema#")
                        .contains(node.get("$schema").asText()))) throw new IllegalArgumentException("Only local Draft7 schemas supported");
        node.elements().forEachRemaining(GrpcCapabilityTransport::rejectExternalSchema);
    }
}
