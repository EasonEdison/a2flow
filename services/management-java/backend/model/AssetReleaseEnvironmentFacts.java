package dev.a2flow.management.model;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Skill 工作台展示的资产环境发布事实。
 *
 * <p>该对象只承载共享发布控制面已经判定的 PRT、ONLINE 和预发实际选择结果，
 * 不参与环境指针解析，也不会写入 Skill 稳定绑定关系。
 */
@Data
@Accessors(chain = true)
public class AssetReleaseEnvironmentFacts {

    private AssetReleaseSourceFact preprod;
    private AssetReleaseSourceFact online;
    private AssetReleaseSourceFact effectivePreprod;
    private Boolean onlineBlocked;
    private String onlineBlockedReason;

    /** 单个环境来源或结构化失败的只读展示事实。 */
    @Data
    @Accessors(chain = true)
    public static class AssetReleaseSourceFact {
        private String environment;
        private String requestedEnvironment;
        private String resolvedEnvironment;
        private String status;
        private Boolean available;
        private String sourceType;
        private String sourceId;
        private Integer version;
        private String digest;
        private String errorCode;
        private String message;
    }
}
