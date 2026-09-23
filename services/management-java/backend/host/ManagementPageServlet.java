package dev.a2flow.management.host;

import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/** 管理页面使用客户端路由；仅显式页面前缀转交入口，不吞掉 API 或静态资源的 404。 */
public final class ManagementPageServlet extends HttpServlet {
    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException, ServletException {
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("X-Content-Type-Options", "nosniff");
        request.getRequestDispatcher("/index.html").forward(request, response);
    }
}
