package dev.a2flow.management.release;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.release.ReleaseModels.GrayReleaseRule;

/**
 * 共享灰度管理请求的结构化解析器。
 *
 * <p>上游是 {@link AssetReleaseApplicationService} 的四个灰度管理方法；本类只负责解析并规范化环境、
 * 百分比和 userId 白名单，不读取运行态 userId、不访问 Repository，也不承担灰度状态迁移。
 */
final class GrayReleaseRequestParser {

    private static final String PARAM_ENVIRONMENT = "environment";
    private static final String PARAM_PERCENTAGE = "percentage";
    private static final String PARAM_USER_ID_WHITELIST = "userIdWhitelist";
    private static final String ERROR_ENVIRONMENT_INVALID = "gray environment must be PRT or ONLINE";
    private static final String ERROR_PERCENTAGE_INVALID = "percentage must be between 0 and 100";
    private static final String ERROR_WHITELIST_INVALID = "userIdWhitelist must contain signed Long decimal userId";
    private static final int MIN_PERCENTAGE = 0;
    private static final int MAX_PERCENTAGE = 100;

    private GrayReleaseRequestParser() {
    }

    static ReleaseEnvironment environment(Map<String, String> params) {
        String value = StringUtils.upperCase(StringUtils.trim(required(params, PARAM_ENVIRONMENT)));
        try {
            return ReleaseEnvironment.valueOf(value);
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(ERROR_ENVIRONMENT_INVALID, exception);
        }
    }

    static GrayReleaseRule rule(Map<String, String> params) {
        int percentage;
        try {
            percentage = Integer.parseInt(required(params, PARAM_PERCENTAGE));
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(ERROR_PERCENTAGE_INVALID, exception);
        }
        if (percentage < MIN_PERCENTAGE || percentage > MAX_PERCENTAGE) {
            throw new IllegalArgumentException(ERROR_PERCENTAGE_INVALID);
        }
        List<Long> whitelist = new ArrayList<>();
        String rawWhitelist = StringUtils.trimToEmpty(params.get(PARAM_USER_ID_WHITELIST));
        if (StringUtils.isNotBlank(rawWhitelist)) {
            for (String rawUserId : rawWhitelist.split(",", -1)) {
                long userId = parseUserId(rawUserId);
                if (!whitelist.contains(userId)) {
                    whitelist.add(userId);
                }
            }
        }
        whitelist.sort(Long::compareTo);
        return new GrayReleaseRule()
                .setPercentage(percentage)
                .setUserIdWhitelist(whitelist);
    }

    private static long parseUserId(String rawUserId) {
        try {
            long userId = dev.a2flow.management.access.UserIds.parseWire(StringUtils.trim(rawUserId));
            return userId;
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(ERROR_WHITELIST_INVALID, exception);
        }
    }

    private static String required(Map<String, String> params, String key) {
        String value = params == null ? null : StringUtils.trimToNull(params.get(key));
        if (value == null) {
            throw new IllegalArgumentException(key + " is required");
        }
        return value;
    }
}
