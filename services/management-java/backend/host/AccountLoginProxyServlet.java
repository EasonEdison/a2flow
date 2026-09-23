package dev.a2flow.management.host;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/** 复用现有账号密码服务，只转发固定登录/退出路由；不实现第二套密码及会话协议。 */
public final class AccountLoginProxyServlet extends HttpServlet {
    private final URI upstream;
    private final ManagementHttpPolicy policy;
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER).build();

    public AccountLoginProxyServlet(String origin, ManagementHttpPolicy policy) {
        this.upstream = URI.create(origin);
        this.policy = policy;
        if (!"http".equals(upstream.getScheme()) || !"127.0.0.1".equals(upstream.getHost())
                || upstream.getPort() < 1 || !upstream.getPath().isEmpty() || upstream.getUserInfo() != null
                || upstream.getQuery() != null || upstream.getFragment() != null) {
            throw new IllegalArgumentException("Account upstream must be an explicit loopback HTTP origin");
        }
    }

    @Override
    protected void service(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("X-Content-Type-Options", "nosniff");
        String path = request.getRequestURI();
        if (!(path.equals("/login") || path.equals("/logout"))
                || !(request.getMethod().equals("GET") || request.getMethod().equals("POST"))) {
            response.sendError(405);
            return;
        }
        try {
            policy.check(request);
            if (request.getQueryString() != null) {
                response.sendError(400);
                return;
            }
            byte[] body = ManagementHttpPolicy.readBody(request);
            var builder = HttpRequest.newBuilder(upstream.resolve(path)).timeout(Duration.ofSeconds(15))
                    .method(request.getMethod(), HttpRequest.BodyPublishers.ofByteArray(body));
            for (String header : java.util.List.of("Content-Type", "Origin", "Sec-Fetch-Site", "Cookie")) {
                var values = java.util.Collections.list(request.getHeaders(header));
                if (values.size() > 1) throw new SecurityException("AMBIGUOUS_REQUEST_HEADER");
                if (!values.isEmpty()) builder.header(header, values.get(0));
            }
            var reply = client.send(builder.build(), HttpResponse.BodyHandlers.ofInputStream());
            byte[] content;
            try (var input = reply.body()) {
                content = input.readNBytes(ManagementHttpPolicy.MAX_BODY_BYTES + 1);
            }
            if (content.length > ManagementHttpPolicy.MAX_BODY_BYTES) throw new IOException("Account response too large");
            String location = reply.headers().firstValue("Location").orElse(null);
            if (location != null && !location.equals("/") && !location.equals("/login")) {
                throw new IOException("Unexpected account redirect");
            }
            response.setStatus(reply.statusCode());
            reply.headers().firstValue("Content-Type").ifPresent(response::setContentType);
            if (location != null) response.setHeader("Location", location);
            for (String cookie : reply.headers().allValues("Set-Cookie")) {
                if (cookie.startsWith("a2flow_management_session=")) response.addHeader("Set-Cookie", cookie);
            }
            response.getOutputStream().write(content);
        } catch (SecurityException failure) {
            response.sendError(403);
        } catch (IllegalArgumentException failure) {
            response.sendError(400);
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            response.sendError(503);
        } catch (IOException failure) {
            // Never print request bodies: the login form contains a password.
            response.sendError(502);
        }
    }
}
