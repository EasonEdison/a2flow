package dev.a2flow.management.lifecycle.publish;

import java.io.IOException;
import java.util.Objects;

import org.springframework.stereotype.Service;

import dev.a2flow.management.release.ReleaseModels.ReleasePublishContext;

/** 只同步完整不可变发布材料到环境隔离的 Runtime DB，不调用业务 RPC。 */
@Service
public final class RuntimeAssetPublisher {
    public record Selection(String kind, String key, String environment) { }
    public record Request(String kind, String key, String environment, String assetKey,
            String sourceId, String sourceDigest, String payloadDigest, String payloadJson, String requestId,
            String expectedServingDigest) { }
    public record Receipt(boolean published, String kind, String key, String environment,
            String sourceId, String sourceDigest, String versionId, String contentDigest,
            String servingDigest, String requestId) { }

    private final HttpRuntimeSkillPublicationAdapter bridge;

    public RuntimeAssetPublisher(HttpRuntimeSkillPublicationAdapter bridge) {
        this.bridge = bridge;
    }

    public Receipt publish(String kind, String key, ReleasePublishContext context) {
        if (context == null || context.getSnapshot() == null || context.getEnvironment() == null) {
            throw new IllegalArgumentException("RUNTIME_PUBLICATION_CONTEXT_REQUIRED");
        }
        try {
            var environment = context.getEnvironment().name();
            var selection = bridge.call("/asset/selection", new Selection(kind, key, environment),
                    HttpRuntimeSkillPublicationAdapter.SelectionResponse.class);
            if (selection.servingDigest() == null || !selection.servingDigest().matches("sha256:[0-9a-f]{64}")) {
                throw new IOException("PUBLICATION_SELECTION_INVALID");
            }
            var request = new Request(kind, key, environment, context.getAssetKey(), context.getSourceId(),
                    context.getSnapshot().getDigest(), "sha256:" +
                        dev.a2flow.management.release.ReleaseDigestUtils.sha256(context.getSnapshot().getPayloadJson()),
                    context.getSnapshot().getPayloadJson(),
                    context.getRequestId(), selection.servingDigest());
            var receipt = bridge.call("/asset/publish", request, Receipt.class);
            if (!receipt.published() || !Objects.equals(receipt.kind(), kind)
                    || !Objects.equals(receipt.key(), key) || !Objects.equals(receipt.environment(), environment)
                    || !Objects.equals(receipt.sourceId(), request.sourceId())
                    || !Objects.equals(receipt.sourceDigest(), request.sourceDigest())
                    || !Objects.equals(receipt.requestId(), request.requestId())
                    || receipt.versionId() == null || receipt.versionId().isBlank()
                    || receipt.contentDigest() == null || !receipt.contentDigest().matches("sha256:[0-9a-f]{64}")) {
                throw new IOException("RUNTIME_PUBLICATION_RECEIPT_INVALID");
            }
            return receipt;
        } catch (IOException exception) {
            throw new IllegalStateException("RUNTIME_PUBLICATION_FAILED", exception);
        }
    }
}
