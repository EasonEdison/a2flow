package dev.a2flow.management.capabilityrpc;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.List;
import com.google.protobuf.*;
import dev.a2flow.management.capabilityrpc.proto.Capability;
import dev.a2flow.management.capabilityrpc.proto.ExecutionContext;
import dev.a2flow.management.capabilityrpc.proto.Environment;
import io.grpc.*;
import io.grpc.protobuf.ProtoUtils;
import io.grpc.stub.ServerCalls;

/** Synthetic business service for the isolated integration environment only. No management state writes. */
public final class SyntheticBusinessGrpc {
    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !args[0].equals("18894")) throw new IllegalArgumentException("Isolated business fixture port required");
        var request = DescriptorProtos.DescriptorProto.newBuilder().setName("Request")
                .addField(field("context", 1, DescriptorProtos.FieldDescriptorProto.Type.TYPE_MESSAGE).setTypeName(".a2flow.capability.v1.ExecutionContext"))
                .addField(field("quantity", 2, DescriptorProtos.FieldDescriptorProto.Type.TYPE_INT64))
                .addField(field("label", 3, DescriptorProtos.FieldDescriptorProto.Type.TYPE_STRING));
        var response = DescriptorProtos.DescriptorProto.newBuilder().setName("Response")
                .addField(field("quantity", 1, DescriptorProtos.FieldDescriptorProto.Type.TYPE_INT64))
                .addField(field("message", 2, DescriptorProtos.FieldDescriptorProto.Type.TYPE_STRING));
        var source = DescriptorProtos.FileDescriptorProto.newBuilder().setName("integration_business.proto").setPackage("integration.business.v1")
                .setSyntax("proto3").addDependency(Capability.getDescriptor().getName()).addMessageType(request).addMessageType(response)
                .addService(DescriptorProtos.ServiceDescriptorProto.newBuilder().setName("Business")
                        .addMethod(DescriptorProtos.MethodDescriptorProto.newBuilder().setName("Invoke")
                                .setInputType(".integration.business.v1.Request").setOutputType(".integration.business.v1.Response"))).build();
        var file = Descriptors.FileDescriptor.buildFrom(source, new Descriptors.FileDescriptor[]{Capability.getDescriptor()});
        var descriptorSet = DescriptorProtos.FileDescriptorSet.newBuilder().addFile(Capability.getDescriptor().toProto()).addFile(file.toProto()).build();
        Files.writeString(Path.of(args[1]), Base64.getEncoder().encodeToString(descriptorSet.toByteArray()));
        var method = file.findServiceByName("Business").findMethodByName("Invoke");
        var rpc = MethodDescriptor.<DynamicMessage, DynamicMessage>newBuilder().setType(MethodDescriptor.MethodType.UNARY)
                .setFullMethodName("integration.business.v1.Business/Invoke")
                .setRequestMarshaller(ProtoUtils.marshaller(DynamicMessage.getDefaultInstance(method.getInputType())))
                .setResponseMarshaller(ProtoUtils.marshaller(DynamicMessage.getDefaultInstance(method.getOutputType()))).build();
        var definition = ServerServiceDefinition.builder("integration.business.v1.Business").addMethod(rpc,
                ServerCalls.asyncUnaryCall((input, observer) -> {
                    try {
                        var message = (DynamicMessage) input.getField(method.getInputType().findFieldByName("context"));
                        var context = ExecutionContext.parseFrom(message.toByteArray());
                        if (!context.hasUserId() || context.getRequestId().isBlank()
                                || (context.getEnvironment() != Environment.PRT && context.getEnvironment() != Environment.ONLINE)
                                || !List.of("PC", "APP", "COMMON").contains(context.getClient())) {
                            observer.onError(Status.UNAUTHENTICATED.withDescription("TRUSTED_CONTEXT_REQUIRED").asRuntimeException()); return;
                        }
                        long quantity = (Long) input.getField(method.getInputType().findFieldByName("quantity"));
                        String label = (String) input.getField(method.getInputType().findFieldByName("label"));
                        observer.onNext(DynamicMessage.newBuilder(method.getOutputType())
                                .setField(method.getOutputType().findFieldByName("quantity"), quantity)
                                .setField(method.getOutputType().findFieldByName("message"), label.isBlank() ? "RPC操作成功" : label).build());
                        observer.onCompleted();
                        System.out.println("BUSINESS_RPC_OK environment=" + context.getEnvironment());
                    } catch (Exception failure) { observer.onError(Status.INVALID_ARGUMENT.withDescription("INVALID_BUSINESS_REQUEST").asRuntimeException()); }
                })).build();
        Server server = TrustedGrpcServer.start("127.0.0.1", 18894, true, null, null, null, List.of(() -> definition));
        Runtime.getRuntime().addShutdownHook(new Thread(server::shutdownNow));
        System.out.println("BUSINESS_RPC_READY");
        server.awaitTermination();
    }
    private static DescriptorProtos.FieldDescriptorProto.Builder field(String name, int number, DescriptorProtos.FieldDescriptorProto.Type type) {
        return DescriptorProtos.FieldDescriptorProto.newBuilder().setName(name).setNumber(number).setType(type).setLabel(DescriptorProtos.FieldDescriptorProto.Label.LABEL_OPTIONAL);
    }
}
