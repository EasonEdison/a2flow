package dev.a2flow.management.config;

import lombok.Data;

/**
 * SkillFactory Authoring Chat 的外部 HTTP 调试地址配置。
 *
 * <p>上游由当前 bizKey 的 {@code propertiesConfig.httpDebugConfig} 提供预发和生产 origin，
 * 下游只允许 Curl Tool 根据用户明确选择的环境拼接请求 path。该配置不保存 Cookie、token、
 * 固定业务 path 或运行态身份，也不允许模型覆盖目标 origin。
 */
@Data
public class SkillFactoryHttpDebugConfig {

    private String preReleaseOrigin;
    private String productionOrigin;
}
