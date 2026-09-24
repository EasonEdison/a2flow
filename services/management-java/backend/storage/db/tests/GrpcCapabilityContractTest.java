package dev.a2flow.management.capabilityrpc;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.function.Consumer;

import com.google.protobuf.DescriptorProtos;
import com.google.protobuf.Descriptors;

/** Descriptor authority checks without network or database access. */
public final class GrpcCapabilityContractTest {
    private static final String AUTHORITY_FILE = "a2flow/capability/v1/capability.proto";
    private static final String CONTENT_SERVICE = "a2flow.content.v1.ContentService";

    public static void main(String[] args) throws Exception {
        String descriptor = Files.readString(contentDescriptor()).strip();
        var method = GrpcCapabilityContract.method(descriptor, CONTENT_SERVICE, "CreateProject", "context");
        check(method.getName().equals("CreateProject"), "real content descriptor did not resolve CreateProject");
        check(method.getService().getFullName().equals(CONTENT_SERVICE), "wrong content service resolved");

        nestedCanonicalJsonNameIsRedundant();
        mustReject(mutateAuthority(descriptor, file -> field(file, "ExecutionContext", "user_id").setNumber(99)));
        mustReject(mutateAuthority(descriptor, file -> field(file, "ExecutionContext", "user_id")
                .setType(DescriptorProtos.FieldDescriptorProto.Type.TYPE_STRING)));
        mustReject(mutateAuthority(descriptor, file -> field(file, "ResolveRequest", "context")
                .setTypeName(".forged.ExecutionContext")));
        mustReject(mutateAuthority(descriptor, file -> file.setPackage("forged.capability.v1")));
        mustReject(mutateAuthority(descriptor, file -> file.getServiceBuilder(0).setName("ForgedExecution")));
        mustReject(mutateAuthority(descriptor, file -> field(file, "ExecutionContext", "user_id")
                .setJsonName("forgedActor")));
        mustReject(withoutAuthority(descriptor));
        System.out.println("GRPC_CAPABILITY_CONTRACT_PASS: canonical json_name compatibility, exact authority, "
                + "real CreateProject descriptor, structural and import rejection");
    }

    private static void nestedCanonicalJsonNameIsRedundant() throws Exception {
        var nested = DescriptorProtos.DescriptorProto.newBuilder().setName("Nested")
                .addField(DescriptorProtos.FieldDescriptorProto.newBuilder()
                        .setName("nested_value").setNumber(1)
                        .setLabel(DescriptorProtos.FieldDescriptorProto.Label.LABEL_OPTIONAL)
                        .setType(DescriptorProtos.FieldDescriptorProto.Type.TYPE_STRING))
                .build();
        var outer = DescriptorProtos.DescriptorProto.newBuilder().setName("Outer")
                .addNestedType(nested).build();
        var authorityProto = DescriptorProtos.FileDescriptorProto.newBuilder()
                .setName("nested-authority.proto").setPackage("authority")
                .setSyntax("proto3").addMessageType(outer).build();
        var authority = Descriptors.FileDescriptor.buildFrom(authorityProto, new Descriptors.FileDescriptor[0]);
        var canonical = authorityProto.toBuilder();
        canonical.getMessageTypeBuilder(0).getNestedTypeBuilder(0).getFieldBuilder(0)
                .setJsonName("nestedValue");
        check(GrpcCapabilityContract.matchesPlatformDescriptor(authority, canonical.build()),
                "canonical nested json_name presence rejected");
        canonical.getMessageTypeBuilder(0).getNestedTypeBuilder(0).getFieldBuilder(0)
                .setJsonName("forgedNestedValue");
        check(!GrpcCapabilityContract.matchesPlatformDescriptor(authority, canonical.build()),
                "noncanonical nested json_name accepted");
    }

    private static String mutateAuthority(String encoded,
            Consumer<DescriptorProtos.FileDescriptorProto.Builder> mutation) throws Exception {
        var set = parse(encoded).toBuilder();
        mutation.accept(authority(set));
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

    private static DescriptorProtos.FileDescriptorProto.Builder authority(
            DescriptorProtos.FileDescriptorSet.Builder set) {
        for (int index = 0; index < set.getFileCount(); index++) {
            if (set.getFile(index).getName().equals(AUTHORITY_FILE)) return set.getFileBuilder(index);
        }
        throw new AssertionError("content descriptor lacks platform authority");
    }

    private static DescriptorProtos.FieldDescriptorProto.Builder field(
            DescriptorProtos.FileDescriptorProto.Builder file, String messageName, String fieldName) {
        for (int messageIndex = 0; messageIndex < file.getMessageTypeCount(); messageIndex++) {
            var message = file.getMessageTypeBuilder(messageIndex);
            if (!message.getName().equals(messageName)) continue;
            for (int fieldIndex = 0; fieldIndex < message.getFieldCount(); fieldIndex++) {
                var field = message.getFieldBuilder(fieldIndex);
                if (field.getName().equals(fieldName)) return field;
            }
        }
        throw new AssertionError("field not found: " + messageName + "." + fieldName);
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
            if (!expected.getMessage().equals(
                    "Exact platform ExecutionContext descriptor required (include imports)")) {
                throw new AssertionError("mutation bypassed authority gate", expected);
            }
            return;
        }
        throw new AssertionError("mutated platform authority was accepted");
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
