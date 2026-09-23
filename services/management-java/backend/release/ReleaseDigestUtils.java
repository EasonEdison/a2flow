package dev.a2flow.management.release;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * 发布快照摘要工具。
 *
 * <p>所有领域 Adapter 使用同一 SHA-256 算法生成内容摘要，避免共享状态机比较不同口径的 digest。
 */
public final class ReleaseDigestUtils {

    private static final String SHA_256 = "SHA-256";

    private ReleaseDigestUtils() {
    }

    /** 对规范化 JSON 文本生成 SHA-256 十六进制摘要。 */
    public static String sha256(String content) {
        try {
            byte[] digest = MessageDigest.getInstance(SHA_256)
                    .digest(String.valueOf(content).getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder(digest.length * 2);
            for (byte value : digest) {
                builder.append(String.format("%02x", value));
            }
            return builder.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is unavailable", e);
        }
    }
}
