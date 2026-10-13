package dev.a2flow.management.managementagent;

import java.util.HashMap;
import java.util.Map;
import org.springframework.web.context.request.AbstractRequestAttributes;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;

/** Bridges one trusted RPC operation to existing request-scoped workspace cleanup. */
public final class ManagementOperationContext implements AutoCloseable {
    private static final ThreadLocal<ManagementAgentGrantStore.Grant> CURRENT = new ThreadLocal<>();
    private final RequestAttributes previous = RequestContextHolder.getRequestAttributes();
    private final OperationAttributes attributes = new OperationAttributes();

    public ManagementOperationContext(ManagementAgentGrantStore.Grant grant) {
        if (CURRENT.get() != null) throw new IllegalStateException("Nested management authority is not allowed");
        CURRENT.set(grant);
        RequestContextHolder.setRequestAttributes(attributes);
    }
    public static ManagementAgentGrantStore.Grant current() { return CURRENT.get(); }
    @Override public void close() {
        try { attributes.requestCompleted(); }
        finally { CURRENT.remove(); RequestContextHolder.setRequestAttributes(previous); }
    }

    private static final class OperationAttributes extends AbstractRequestAttributes {
        private final Map<String, Object> values = new HashMap<>();
        @Override public Object getAttribute(String name, int scope) { requireRequest(scope); return values.get(name); }
        @Override public void setAttribute(String name, Object value, int scope) { requireRequest(scope); values.put(name, value); }
        @Override public void removeAttribute(String name, int scope) { requireRequest(scope); values.remove(name); removeRequestDestructionCallback(name); }
        @Override public String[] getAttributeNames(int scope) { requireRequest(scope); return values.keySet().toArray(String[]::new); }
        @Override public void registerDestructionCallback(String name, Runnable callback, int scope) { requireRequest(scope); registerRequestDestructionCallback(name, callback); }
        @Override public Object resolveReference(String key) { return null; }
        @Override public String getSessionId() { throw new IllegalStateException("RPC operations have no HTTP session"); }
        @Override public Object getSessionMutex() { return this; }
        @Override protected void updateAccessedSessionAttributes() { }
        private static void requireRequest(int scope) { if (scope != SCOPE_REQUEST) throw new IllegalArgumentException("Only operation request scope is supported"); }
    }
}
