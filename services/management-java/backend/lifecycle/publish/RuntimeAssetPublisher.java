package dev.a2flow.management.lifecycle.publish;

import java.io.IOException;
import org.springframework.stereotype.Service;
import dev.a2flow.management.release.ReleaseModels.ReleasePublishContext;

/** Retains complete compiler artifacts in the selected environment database. */
@Service
public final class RuntimeAssetPublisher {
    public record Receipt(boolean published, String kind, String key, String environment,
            String sourceId, String sourceDigest, String versionId, String contentDigest,
            String servingDigest, String requestId) { }
    private final RuntimePublicationStore store;
    public RuntimeAssetPublisher(RuntimePublicationStore store) { this.store = store; }
    public Receipt publish(String kind, String key, ReleasePublishContext context) {
        if (context == null || context.getSnapshot() == null || context.getEnvironment() == null) {
            throw new IllegalArgumentException("RUNTIME_PUBLICATION_CONTEXT_REQUIRED");
        }
        try {
            String environment = context.getEnvironment().name();
            var request = PublicationJson.object("kind", kind, "key", key, "environment", environment,
                    "assetKey", context.getAssetKey(), "sourceId", context.getSourceId(),
                    "sourceDigest", context.getSnapshot().getDigest(), "payloadDigest",
                    PublicationJson.digest(context.getSnapshot().getPayloadJson().getBytes(java.nio.charset.StandardCharsets.UTF_8)),
                    "payloadJson", context.getSnapshot().getPayloadJson(), "requestId", context.getRequestId());
            var definition = PublicationJson.object("runtimeProfile", "a2flow.java-rpc.v1");
            for (String field : new String[]{"assetKey", "sourceId", "sourceDigest", "payloadDigest", "payloadJson"}) {
                definition.set(field, request.get(field));
            }
            var deps = PublicationMaterial.javaDependencies(kind, key, definition);
            String version = "java-" + PublicationJson.hash(PublicationJson.bytes(
                    PublicationJson.array(context.getSourceId(), context.getSnapshot().getDigest())));
            String receiptId = "runtime:" + PublicationJson.hash(PublicationJson.bytes(
                    PublicationJson.array(kind, key, context.getRequestId())));
            var result = store.publish(kind, key, environment, receiptId, request, version, definition, deps,
                    store.selection(kind, key, environment));
            return new Receipt(true, kind, key, environment, context.getSourceId(), context.getSnapshot().getDigest(),
                    version, result.path("contentDigest").asText(), result.path("servingDigest").asText(), context.getRequestId());
        } catch (IOException exception) { throw new IllegalStateException("RUNTIME_PUBLICATION_FAILED", exception); }
    }
}
