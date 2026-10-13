package dev.a2flow.management.managementagent;

import java.security.SecureRandom;
import java.time.Clock;
import java.util.Base64;
import java.util.concurrent.ConcurrentHashMap;
import dev.a2flow.management.access.ManagementIdentityProvider;

/** Short-lived opaque callback authority; never serialized to browsers or model messages. */
public final class ManagementAgentGrantStore {
    private static final long TTL_MILLIS = 30 * 60 * 1000L;
    private static final int MAX_GRANTS = 2048;
    private final ConcurrentHashMap<String, Grant> grants = new ConcurrentHashMap<>();
    private final SecureRandom random = new SecureRandom();
    private final Clock clock = Clock.systemUTC();

    public synchronized String issue(ManagementIdentityProvider identity, String conversationId, String requestId) {
        if (!identity.isAdministrator()) throw new SecurityException("ADMIN_REQUIRED");
        long now = clock.millis();
        grants.entrySet().removeIf(entry -> entry.getValue().expiresAt() <= now);
        for (var entry : grants.entrySet()) {
            Grant existing = entry.getValue();
            if (existing.namespace().equals(identity.namespace()) && existing.userId() == identity.userId()
                    && existing.conversationId().equals(conversationId) && existing.parentRequestId().equals(requestId)
                    && existing.expiresAt() > now + 60_000) return entry.getKey();
        }
        if (grants.size() >= MAX_GRANTS) throw new IllegalStateException("MANAGEMENT_AGENT_CAPACITY");
        byte[] token = new byte[32];
        random.nextBytes(token);
        String encoded = Base64.getUrlEncoder().withoutPadding().encodeToString(token);
        grants.put(encoded, new Grant(identity.namespace(), identity.userId(), conversationId, requestId, now + TTL_MILLIS));
        return encoded;
    }

    public Grant resolve(String token) {
        Grant grant = token == null ? null : grants.get(token);
        if (grant == null || grant.expiresAt() <= clock.millis()) {
            if (token != null) grants.remove(token);
            throw new SecurityException("MANAGEMENT_AGENT_GRANT_EXPIRED");
        }
        return grant;
    }

    public record Grant(String namespace, long userId, String conversationId, String parentRequestId, long expiresAt) {
        public void requireConversation(String supplied) {
            if (conversationId == null || conversationId.isBlank() || !conversationId.equals(supplied)) {
                throw new SecurityException("MANAGEMENT_AGENT_GRANT_SCOPE_INVALID");
            }
        }
    }
}
