package dev.a2flow.management.capabilityrpc;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.function.Consumer;

import com.google.protobuf.DescriptorProtos;

/** Descriptor wire-compatibility checks without network or database access. */
public final class GrpcCapabilityContractTest {
    private static final String AUTHORITY_FILE = "a2flow/capability/v1/capability.proto";
    private static final String CONTENT_SERVICE = "a2flow.content.v1.ContentService";

    public static void main(String[] args) throws Exception {
        String descriptor = Files.readString(contentDescriptor()).strip();
        var method = GrpcCapabilityContract.method(descriptor, CONTENT_SERVICE, "CreateProject", "context");
        check(method.getName().equals("CreateProject"), "real content descriptor did not resolve CreateProject");
        check(method.getService().getFullName().equals(CONTENT_SERVICE), "wrong content service resolved");

        mustAccept(mutateAuthority(descriptor, file -> executionContext(file).addField(
                DescriptorProtos.FieldDescriptorProto.newBuilder()
                        .setName("trace_hint").setJsonName("traceHint").setNumber(100)
                        .setLabel(DescriptorProtos.FieldDescriptorProto.Label.LABEL_OPTIONAL)
                        .setType(DescriptorProtos.FieldDescriptorProto.Type.TYPE_STRING))));
        mustAccept(mutateAuthority(descriptor, file -> file.addMessageType(
                DescriptorProtos.DescriptorProto.newBuilder().setName("UnrelatedMetadata")
                        .addField(DescriptorProtos.FieldDescriptorProto.newBuilder()
                                .setName("label").setNumber(1)
                                .setLabel(DescriptorProtos.FieldDescriptorProto.Label.LABEL_OPTIONAL)
                                .setType(DescriptorProtos.FieldDescriptorProto.Type.TYPE_STRING)))));
        mustAccept(mutateAuthority(descriptor, file -> file.getServiceBuilder(0).addMethod(
                DescriptorProtos.MethodDescriptorProto.newBuilder().setName("Inspect")
                        .setInputType(".a2flow.capability.v1.ResolveRequest")
                        .setOutputType(".a2flow.capability.v1.ResolveResponse"))));
        mustAccept(mutateAuthority(descriptor, file -> file.getServiceBuilder(0)
                .setName("UnrelatedCapabilityExecution")));
        mustAccept(mutateAuthority(descriptor, file -> {
            field(file, "ExecutionContext", "user_id").setJsonName("userId");
            field(file, "ExecutionContext", "environment").setJsonName("environment");
            field(file, "ExecutionContext", "request_id").setJsonName("requestId");
            field(file, "ExecutionContext", "client").setJsonName("client");
        }));
        mustAccept(mutateAuthority(descriptor, file -> {
            field(file, "ExecutionContext", "user_id").setJsonName("actor");
            field(file, "ExecutionContext", "environment").setJsonName("lane");
            field(file, "ExecutionContext", "request_id").setJsonName("correlation");
            field(file, "ExecutionContext", "client").setJsonName("surface");
        }));
        mustRejectContext(mutateAuthority(descriptor, file -> field(file, "ExecutionContext", "user_id").setNumber(99)));
        mustRejectContext(mutateAuthority(descriptor, file -> field(file, "ExecutionContext", "user_id")
                .setType(DescriptorProtos.FieldDescriptorProto.Type.TYPE_STRING)));
        mustRejectContext(mutateAuthority(descriptor, file -> field(file, "ExecutionContext", "client")
                .setLabel(DescriptorProtos.FieldDescriptorProto.Label.LABEL_REPEATED)));
        mustRejectContext(mutateAuthority(descriptor, file -> enumValue(file, "Environment", "PRT").setNumber(7)));
        mustRejectContext(mutateAuthority(descriptor, file -> enumValue(file, "Environment", "ONLINE").setNumber(8)));
        mustRejectContext(mutateAuthority(descriptor, GrpcCapabilityContractTest::shareIdentityOneof));
        mustReject(withoutAuthority(descriptor));
        System.out.println("GRPC_CAPABILITY_CONTRACT_PASS: required method/context wire compatibility, "
                + "compatible descriptor growth, json_name independence, identity type/number/enum/oneof rejection");
    }

    private static void shareIdentityOneof(DescriptorProtos.FileDescriptorProto.Builder file) {
        var context = executionContext(file);
        var synthetic = context.getOneofDecl(0);
        context.clearOneofDecl();
        context.addOneofDecl(DescriptorProtos.OneofDescriptorProto.newBuilder().setName("request_identity"));
        context.addOneofDecl(synthetic);
        field(file, "ExecutionContext", "user_id").setOneofIndex(1);
        field(file, "ExecutionContext", "request_id").setOneofIndex(0);
        field(file, "ExecutionContext", "client").setOneofIndex(0);
    }

    private static String mutateAuthority(String encoded,
            Consumer<DescriptorProtos.FileDescriptorProto.Builder> mutation) throws Exception {
        return mutateFile(encoded, AUTHORITY_FILE, mutation);
    }

    private static String mutateFile(String encoded, String fileName,
            Consumer<DescriptorProtos.FileDescriptorProto.Builder> mutation) throws Exception {
        var set = parse(encoded).toBuilder();
        mutation.accept(file(set, fileName));
        return Base64.getEncoder().encodeToString(set.build().toByteArray());
    }

    private static String withoutAuthority(String encoded) throws Exception {
        var original = parse(encoded);
        var filtered = DescriptorProtos.FileDescriptorSet.newBuilder();
        for (var file : original.getFileList()) {
            if (!file.getName().equals(AUTHORITY_FILE)) filtered.addFile(file);
        }
        return Base64.getEncoder().encodeToString(filtered.build().toByteArray());
    }

    private static DescriptorProtos.FileDescriptorSet parse(String encoded) throws Exception {
        return DescriptorProtos.FileDescriptorSet.parseFrom(Base64.getDecoder().decode(encoded));
    }

    private static DescriptorProtos.FileDescriptorProto.Builder file(
            DescriptorProtos.FileDescriptorSet.Builder set, String fileName) {
        for (int index = 0; index < set.getFileCount(); index++) {
            if (set.getFile(index).getName().equals(fileName)) return set.getFileBuilder(index);
        }
        throw new AssertionError("descriptor file not found: " + fileName);
    }

    private static DescriptorProtos.FieldDescriptorProto.Builder field(
            DescriptorProtos.FileDescriptorProto.Builder file, String messageName, String fieldName) {
        var message = message(file, messageName);
        for (int fieldIndex = 0; fieldIndex < message.getFieldCount(); fieldIndex++) {
            var field = message.getFieldBuilder(fieldIndex);
            if (field.getName().equals(fieldName)) return field;
        }
        throw new AssertionError("field not found: " + messageName + "." + fieldName);
    }

    private static DescriptorProtos.DescriptorProto.Builder executionContext(
            DescriptorProtos.FileDescriptorProto.Builder file) {
        return message(file, "ExecutionContext");
    }

    private static DescriptorProtos.DescriptorProto.Builder message(
            DescriptorProtos.FileDescriptorProto.Builder file, String messageName) {
        for (int index = 0; index < file.getMessageTypeCount(); index++) {
            var message = file.getMessageTypeBuilder(index);
            if (message.getName().equals(messageName)) return message;
        }
        throw new AssertionError("message not found: " + messageName);
    }

    private static DescriptorProtos.EnumValueDescriptorProto.Builder enumValue(
            DescriptorProtos.FileDescriptorProto.Builder file, String enumName, String valueName) {
        for (int enumIndex = 0; enumIndex < file.getEnumTypeCount(); enumIndex++) {
            var candidate = file.getEnumTypeBuilder(enumIndex);
            if (!candidate.getName().equals(enumName)) continue;
            for (int valueIndex = 0; valueIndex < candidate.getValueCount(); valueIndex++) {
                var value = candidate.getValueBuilder(valueIndex);
                if (value.getName().equals(valueName)) return value;
            }
        }
        throw new AssertionError("enum value not found: " + enumName + "." + valueName);
    }

    private static Path contentDescriptor() {
        for (Path candidate : new Path[] {
                Path.of("deploy", "reading_content", "content-descriptor.txt"),
                Path.of("..", "..", "deploy", "reading_content", "content-descriptor.txt")}) {
            if (Files.isRegularFile(candidate)) return candidate;
        }
        throw new AssertionError("run from repository root or services/management-java");
    }

    private static void mustReject(String descriptor) {
        try {
            GrpcCapabilityContract.method(descriptor, CONTENT_SERVICE, "CreateProject", "context");
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("wire-incompatible platform context was accepted");
    }

    private static void mustRejectContext(String descriptor) {
        try {
            GrpcCapabilityContract.method(descriptor, CONTENT_SERVICE, "CreateProject", "context");
        } catch (IllegalArgumentException expected) {
            check(expected.getMessage().startsWith("Platform ExecutionContext is wire-incompatible:"),
                    "context mutation failed outside the wire-compatibility gate: " + expected.getMessage());
            return;
        }
        throw new AssertionError("wire-incompatible platform context was accepted");
    }

    private static void mustAccept(String descriptor) {
        GrpcCapabilityContract.method(descriptor, CONTENT_SERVICE, "CreateProject", "context");
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
