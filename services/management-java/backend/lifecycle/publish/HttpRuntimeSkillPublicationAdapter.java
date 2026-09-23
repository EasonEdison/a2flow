package dev.a2flow.management.lifecycle.publish;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Base64;
import java.util.Objects;
import com.fasterxml.jackson.databind.JsonNode;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.support.JsonSupport;

/** Calls the authenticated, validator-backed management publication bridge; never invokes an Agent. */
@Service
public final class HttpRuntimeSkillPublicationAdapter implements RuntimeSkillPublicationPort {
    public record SelectionRequest(String key, String environment) { }
    public record SelectionResponse(String servingDigest) { }
    public record ErrorResponse(String error) { }
    public record PublicationRequest(String key, String environment, String sourceId, String sourceDigest,
            JsonNode snapshot, String requestId, String packageDigest, String packageBase64,
            String expectedServingDigest) { }
    public record PublicationResponse(boolean published, String assetKey, String environment,
            String packageDigest, String versionId, String contentDigest, String servingDigest,
            String requestId) { }
    private final URI base;
    private final String token;
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER).build();

    public HttpRuntimeSkillPublicationAdapter(Environment environment) {
        base = URI.create(environment.getRequiredProperty("A2FLOW_PUBLICATION_BRIDGE_URL"));
        if (!"http".equals(base.getScheme()) || !"127.0.0.1".equals(base.getHost())
                || base.getUserInfo() != null || base.getQuery() != null || base.getFragment() != null
                || !(base.getPath().isEmpty() || "/".equals(base.getPath()))) {
            throw new IllegalArgumentException("PUBLICATION_BRIDGE_LOOPBACK_URL_REQUIRED");
        }
        token = environment.getRequiredProperty("A2FLOW_PUBLICATION_BRIDGE_TOKEN");
        if (token.length() < 32 || token.contains("\n") || token.contains("\r")) {
            throw new IllegalArgumentException("PUBLICATION_BRIDGE_TOKEN_INVALID");
        }
    }

    @Override
    public Receipt publish(SkillDraft draft, ReleaseArtifact artifact, byte[] packageBytes, int version,
            String environment, SkillPublicationInput input) throws IOException {
        SelectionResponse selected = call("/selection", new SelectionRequest(draft.getSkillCode(), environment),
                SelectionResponse.class);
        if (!digest(selected.servingDigest())) throw new IOException("PUBLICATION_SELECTION_INVALID");
        PublicationRequest request = new PublicationRequest(draft.getSkillCode(), environment, input.sourceId(),
                input.sourceDigest(), JsonSupport.fromJSON(input.snapshotJson(), JsonNode.class), input.requestId(),
                artifact.getPackageDigest(), Base64.getEncoder().encodeToString(packageBytes), selected.servingDigest());
        PublicationResponse result = call("/publish", request, PublicationResponse.class);
        if (!result.published() || !Objects.equals(request.key(), result.assetKey())
                || !Objects.equals(environment, result.environment())
                || !Objects.equals(request.packageDigest(), result.packageDigest())
                || !Objects.equals(input.requestId(), result.requestId())
                || result.versionId() == null || result.versionId().isBlank()
                || !digest(result.contentDigest()) || !digest(result.servingDigest())) {
            throw new IOException("PUBLICATION_RECEIPT_INVALID");
        }
        return new Receipt(result.assetKey(), result.environment(), result.packageDigest(), result.versionId(),
                result.contentDigest(), result.servingDigest(), result.requestId());
    }

    <T> T call(String path, Object value, Class<T> responseType) throws IOException {
        HttpRequest request = HttpRequest.newBuilder(base.resolve(path)).timeout(Duration.ofSeconds(40))
                .header("Authorization", "Bearer " + token).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(JsonSupport.toJSON(value))).build();
        try {
            HttpResponse<java.io.InputStream> response = client.send(request, HttpResponse.BodyHandlers.ofInputStream());
            byte[] bytes;
            try (java.io.InputStream body = response.body()) { bytes = body.readNBytes(65_537); }
            if (bytes.length > 65_536) throw new IOException("PUBLICATION_RESPONSE_TOO_LARGE");
            String json = new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
            if (response.statusCode() != 200) {
                ErrorResponse error = JsonSupport.fromJSON(json, ErrorResponse.class);
                String code = error == null ? null : error.error();
                throw new IOException(code != null && code.matches("[A-Z0-9_]{1,96}")
                        ? code : "PUBLICATION_BRIDGE_REJECTED");
            }
            T result = JsonSupport.fromJSON(json, responseType);
            if (result == null) throw new IOException("PUBLICATION_RESPONSE_INVALID");
            return result;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IOException("PUBLICATION_INTERRUPTED_OUTCOME_UNKNOWN");
        } catch (IllegalArgumentException exception) {
            throw new IOException("PUBLICATION_RESPONSE_INVALID");
        }
    }

    private static boolean digest(String value) {
        return value != null && value.matches("sha256:[0-9a-f]{64}");
    }
}
