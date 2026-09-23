package dev.a2flow.management.access;

import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
import org.springframework.web.context.WebApplicationContext;

/** 每次请求只解析一次可信会话。Cookie 中不接受裸 userId、角色或环境。 */
@Component
@Scope(value = WebApplicationContext.SCOPE_REQUEST, proxyMode = ScopedProxyMode.INTERFACES)
public class CookieSessionIdentityProvider implements ManagementIdentityProvider {
    private final String namespace;
    private final DatabaseSessionIdentityResolver.Principal principal;

    public CookieSessionIdentityProvider(HttpServletRequest request,
            DatabaseSessionIdentityResolver resolver, Environment environment) {
        namespace = environment.getRequiredProperty("A2FLOW_MANAGEMENT_NAMESPACE");
        if (namespace.isBlank()) throw new IllegalStateException("Management namespace is required");
        String token = null;
        Cookie[] cookies = request.getCookies();
        if (cookies != null) {
            for (Cookie cookie : cookies) {
                if ("a2flow_management_session".equals(cookie.getName())) {
                    if (token != null) throw new SecurityException("AMBIGUOUS_SESSION_COOKIE");
                    token = cookie.getValue();
                }
            }
        }
        principal = resolver.resolve(token);
    }

    @Override public String namespace() { return namespace; }
    @Override public long userId() { return principal.userId(); }
    @Override public boolean isAdministrator() { return principal.isAdministrator(); }
}
