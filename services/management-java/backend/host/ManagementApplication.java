package dev.a2flow.management.host;

import java.nio.file.Files;
import org.apache.catalina.startup.Tomcat;
import org.springframework.web.context.ContextLoaderListener;
import org.springframework.web.context.request.RequestContextListener;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import dev.a2flow.management.config.ManualManagementConfiguration;

/** 独立手填 HTTP 与受信 Runtime gRPC 宿主，仅监听本机；不建表、不创建默认账号。 */
public final class ManagementApplication {
    private ManagementApplication() { }

    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(System.getenv().getOrDefault("A2FLOW_MANAGEMENT_PORT", "8790"));
        if (port < 1 || port > 65535) throw new IllegalArgumentException("Invalid management port");
        Tomcat tomcat = new Tomcat();
        tomcat.setBaseDir(Files.createTempDirectory("a2flow-management-tomcat-").toString());
        tomcat.setPort(port);
        tomcat.getConnector().setProperty("address", "127.0.0.1");
        tomcat.getConnector().setMaxPostSize(ManagementHttpPolicy.MAX_BODY_BYTES);
        String staticDirectory = System.getenv("A2FLOW_MANAGEMENT_STATIC_DIR");
        String documentRoot = staticDirectory == null ? Files.createTempDirectory("a2flow-management-web-").toString()
                : java.nio.file.Path.of(staticDirectory).toRealPath().toString();
        var web = tomcat.addContext("", documentRoot);
        // addContext does not install the default web.xml MIME mappings.
        web.addMimeMapping("html", "text/html");
        web.addMimeMapping("js", "text/javascript");
        web.addMimeMapping("mjs", "text/javascript");
        web.addMimeMapping("css", "text/css");
        web.addMimeMapping("json", "application/json");
        web.addMimeMapping("svg", "image/svg+xml");
        web.addMimeMapping("png", "image/png");
        web.addMimeMapping("ico", "image/vnd.microsoft.icon");
        web.addMimeMapping("woff", "font/woff");
        web.addMimeMapping("woff2", "font/woff2");
        web.setParentClassLoader(ManagementApplication.class.getClassLoader());
        var application = new AnnotationConfigWebApplicationContext();
        application.register(ManualManagementConfiguration.class);
        var policy = new ManagementHttpPolicy(application.getEnvironment());
        web.setApplicationLifecycleListeners(new Object[] {new ContextLoaderListener(application)});
        web.setApplicationEventListeners(new Object[] {new RequestContextListener()});
        Tomcat.addServlet(web, "management", new ManagementHttpServlet()).setLoadOnStartup(1);
        web.addServletMappingDecoded("/api/management/v2/*", "management");
        String accountOrigin = application.getEnvironment().getRequiredProperty("A2FLOW_ACCOUNT_LOGIN_ORIGIN");
        Tomcat.addServlet(web, "account", new AccountLoginProxyServlet(accountOrigin, policy)).setLoadOnStartup(1);
        web.addServletMappingDecoded("/login", "account");
        web.addServletMappingDecoded("/logout", "account");
        if (staticDirectory != null) {
            var staticServlet = Tomcat.addServlet(web, "static", "org.apache.catalina.servlets.DefaultServlet");
            staticServlet.addInitParameter("readonly", "true");
            staticServlet.addInitParameter("listings", "false");
            web.addServletMappingDecoded("/", "static");
            web.addWelcomeFile("index.html");
            Tomcat.addServlet(web, "management-pages", new ManagementPageServlet());
            web.addServletMappingDecoded("/management", "management-pages");
            web.addServletMappingDecoded("/management/*", "management-pages");
        }
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try { tomcat.stop(); tomcat.destroy(); } catch (Exception ignored) { }
        }, "management-shutdown"));
        tomcat.start();
        if (!web.getState().isAvailable()) {
            tomcat.stop();
            tomcat.destroy();
            throw new IllegalStateException("Management application context failed to start");
        }
        tomcat.getServer().await();
    }
}
