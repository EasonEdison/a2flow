package dev.a2flow.management.agentcore.runtime.util;

import java.nio.file.Path;

/**

 * Created on 2026-04-25
 */
public class PathUtils {

    /**
     * 检查路径是否在工作空间内（安全检查）
     */
    public static boolean isWithinWorkspace(Path path, Path workspacePath) {
        return path.toAbsolutePath().normalize().startsWith(workspacePath);
    }

    /**
     * 解析相对工作空间的路径
     */
    public static Path resolve(String relativePath, Path workspacePath) {
        return workspacePath.resolve(relativePath).normalize();
    }
}
