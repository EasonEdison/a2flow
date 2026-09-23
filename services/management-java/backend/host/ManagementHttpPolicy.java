package dev.a2flow.management.host;

import java.io.IOException;
import java.net.URI;
import java.util.Arrays;
import java.util.Collections;
import java.util.Set;
import java.util.stream.Collectors;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.core.env.Environment;

/** HTTP边界：来源、身份字段和请求体大小由服务端统一约束。 */
public final class ManagementHttpPolicy {
    public static final int MAX_BODY_BYTES = 2 * 1024 * 1024;
    private static final Set<String> IDENTITY_HEADERS = Set.of("authorization", "x-user-id", "x-role",
            "x-roles", "x-environment", "x-a2flow-user-id", "x-a2flow-role", "x-a2flow-roles", "x-a2flow-environment");
    private final Set<String> origins;

    public ManagementHttpPolicy(Environment environment) {
        origins = Arrays.stream(environment.getRequiredProperty("A2FLOW_MANAGEMENT_BROWSER_ORIGINS").split(","))
                .map(String::trim).collect(Collectors.toUnmodifiableSet());
        for (String origin : origins) {
            URI uri = URI.create(origin);
            if (!("http".equals(uri.getScheme()) || "https".equals(uri.getScheme()))
                    || uri.getHost() == null || uri.getUserInfo() != null || uri.getQuery() != null
                    || uri.getFragment() != null || !uri.getPath().isEmpty()) {
                throw new IllegalArgumentException("Browser origins must be exact HTTP(S) origins");
            }
        }
    }

    public void check(HttpServletRequest request) {
        for (String name : Collections.list(request.getHeaderNames())) {
            if (IDENTITY_HEADERS.contains(name.toLowerCase(java.util.Locale.ROOT))) {
                throw new SecurityException("CLIENT_IDENTITY_FIELDS_NOT_ALLOWED");
            }
        }
        if (!"GET".equals(request.getMethod()) && !"HEAD".equals(request.getMethod())) {
            var values = Collections.list(request.getHeaders("Origin"));
            if (values.size() != 1 || !origins.contains(values.get(0))) {
                throw new SecurityException("ACCOUNT_ORIGIN_REQUIRED");
            }
            String site = request.getHeader("Sec-Fetch-Site");
            if (site != null && !site.equals("same-origin")) throw new SecurityException("ACCOUNT_ORIGIN_REQUIRED");
        }
    }

    public static byte[] readBody(HttpServletRequest request) throws IOException {
        byte[] bytes = request.getInputStream().readNBytes(MAX_BODY_BYTES + 1);
        if (bytes.length > MAX_BODY_BYTES) throw new IllegalArgumentException("REQUEST_TOO_LARGE");
        return bytes;
    }
}
