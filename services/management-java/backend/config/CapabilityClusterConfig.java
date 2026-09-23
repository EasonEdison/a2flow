package dev.a2flow.management.config;

import java.util.regex.Pattern;

import org.apache.commons.lang3.StringUtils;

import lombok.Data;

/**
 * 业务能力集群的动态环境地址配置。
 *
 * <p>由 sellerdata 类型化 KConf 提供，页面只展示该配置；执行器每次调用重新读取，
 * 已发布版本仅保存集群标识，不冻结地址。配置缺失或非法必须拒绝调用，不能回退其他集群。
 */
@Data
public class CapabilityClusterConfig {

    private static final Pattern HOST_PATTERN = Pattern.compile("[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?");
    private static final int MAX_PORT = 65535;
    private static final String PORT_SEPARATOR = ":";
    private static final String ERROR_INVALID_ADDRESS = "业务能力集群环境地址或端口配置无效";

    private String displayName;
    private String preReleaseHost;
    private Integer preReleasePort;
    private String productionHost;
    private Integer productionPort;

    /** 按可信环境解析当前配置，主机与端口分别校验后组合，禁止包含协议、路径或凭证。 */
    public String resolveAuthority(boolean online) {
        String host = online ? productionHost : preReleaseHost;
        Integer port = online ? productionPort : preReleasePort;
        if (StringUtils.isBlank(displayName) || host == null || !HOST_PATTERN.matcher(host).matches()
                || port == null || port < 1 || port > MAX_PORT) {
            throw new IllegalArgumentException(ERROR_INVALID_ADDRESS);
        }
        return host + PORT_SEPARATOR + port;
    }
}
