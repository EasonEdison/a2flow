package dev.a2flow.management.capabilityrpc;

import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import com.google.protobuf.DescriptorProtos;
import com.google.protobuf.Descriptors;
import dev.a2flow.management.capabilityrpc.proto.Capability;

/** Registered descriptor is data, never downloaded code or reflection from a model-selected target. */
public final class GrpcCapabilityContract {
    private GrpcCapabilityContract() { }
    public static void validateBinding(Map<String, Object> binding) {
        if (!"GRPC".equals(binding.get("bindingType"))) throw new IllegalArgumentException("GRPC binding required");
        Set<String> allowed = Set.of("bindingType", "target", "timeoutMs", "maxResponseBytes", "idempotency",
                "responsePolicy", "requestMappingsJson", "contextMappingsJson");
        if (!allowed.containsAll(binding.keySet())) throw new IllegalArgumentException("Unknown/HTTP execution binding fields forbidden");
        if (!(binding.get("target") instanceof Map<?, ?> target)) throw new IllegalArgumentException("GRPC target required");
        if (!Set.of("targetKey", "serviceName", "methodName", "descriptorSetBase64", "contextField").containsAll(target.keySet())) {
            throw new IllegalArgumentException("Unknown/HTTP target fields forbidden");
        }
        for (String key : Set.of("targetKey", "serviceName", "methodName", "descriptorSetBase64", "contextField")) {
            if (!(target.get(key) instanceof String value) || value.isBlank()) throw new IllegalArgumentException(key + " required");
        }
        if (!((String) target.get("targetKey")).matches("[A-Za-z][A-Za-z0-9_-]{0,63}")) {
            throw new IllegalArgumentException("targetKey must be a configuration key, not an address");
        }
        if (binding.containsKey("idempotency") && !"NONE".equals(binding.get("idempotency"))) throw new IllegalArgumentException("Only NONE idempotency supported");
        if (binding.containsKey("responsePolicy") && !"ORIGINAL".equals(binding.get("responsePolicy"))) throw new IllegalArgumentException("Only ORIGINAL responsePolicy supported");
        bounded(binding.get("timeoutMs"), 3000, 120000, "timeoutMs");
        bounded(binding.get("maxResponseBytes"), 1048576, 5242880, "maxResponseBytes");
        method((String) target.get("descriptorSetBase64"), (String) target.get("serviceName"),
                (String) target.get("methodName"), (String) target.get("contextField"));
    }

    private static int bounded(Object value, int defaultValue, int max, String name) {
        try {
            int result = value == null ? defaultValue : new java.math.BigDecimal(value.toString()).intValueExact();
            if (result <= 0 || result > max) throw new IllegalArgumentException(name + " out of range");
            return result;
        } catch (ArithmeticException | NumberFormatException failure) { throw new IllegalArgumentException(name + " must be an exact integer", failure); }
    }

    public static Descriptors.MethodDescriptor method(String base64, String service, String method, String contextField) {
        try {
            if (base64 == null || base64.length() > 2_800_000) throw new IllegalArgumentException("Descriptor set exceeds limit");
            var set = DescriptorProtos.FileDescriptorSet.parseFrom(Base64.getDecoder().decode(base64));
            Map<String, DescriptorProtos.FileDescriptorProto> pending = new LinkedHashMap<>();
            for (var file : set.getFileList()) if (pending.put(file.getName(), file) != null) throw new IllegalArgumentException("Duplicate descriptor file");
            Map<String, Descriptors.FileDescriptor> resolved = new LinkedHashMap<>();
            // Context's exact descriptor is owned by the platform, not by the capability author.
            var authority = Capability.getDescriptor();
            if (!authority.toProto().equals(pending.get(authority.getName()))) throw new IllegalArgumentException("Exact platform ExecutionContext descriptor required (include imports)");
            while (!pending.isEmpty()) {
                boolean progress = false;
                var iterator = pending.entrySet().iterator();
                while (iterator.hasNext()) {
                    var entry = iterator.next();
                    if (!resolved.keySet().containsAll(entry.getValue().getDependencyList())) continue;
                    var dependencies = entry.getValue().getDependencyList().stream().map(resolved::get).toArray(Descriptors.FileDescriptor[]::new);
                    resolved.put(entry.getKey(), Descriptors.FileDescriptor.buildFrom(entry.getValue(), dependencies));
                    iterator.remove(); progress = true;
                }
                if (!progress) throw new IllegalArgumentException("Descriptor dependency missing or cyclic");
            }
            for (var file : resolved.values()) for (var candidate : file.getServices()) {
                if (!candidate.getFullName().equals(service)) continue;
                var selected = candidate.findMethodByName(method);
                if (selected == null || selected.isClientStreaming() || selected.isServerStreaming()) throw new IllegalArgumentException("Registered unary method required");
                var field = selected.getInputType().findFieldByName(contextField);
                if (field == null || field.isRepeated() || field.getJavaType() != Descriptors.FieldDescriptor.JavaType.MESSAGE
                        || !field.getMessageType().getFullName().equals("a2flow.capability.v1.ExecutionContext")) {
                    throw new IllegalArgumentException("Request contextField must reference platform ExecutionContext");
                }
                return selected;
            }
            throw new IllegalArgumentException("Service not found in descriptor set");
        } catch (com.google.protobuf.InvalidProtocolBufferException | Descriptors.DescriptorValidationException e) {
            throw new IllegalArgumentException("Invalid descriptor set", e);
        }
    }
}
