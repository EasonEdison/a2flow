package dev.a2flow.management.aicoding.run;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory Authoring Chat 单次运行状态。
 *
 * <p>该对象由 {@link SkillFactoryRunControlService} 根据 Authoring Chat DB 开始/终态事件和 Redis
 * 取消信号推导，供流式执行线程、取消接口和页面刷新后的状态查询共享。它只描述运行生命周期，
 * 不保存用户输入、模型输出或敏感上下文。
 */
@Data
@Accessors(chain = true)
public class SkillFactoryRunStatus {

    public static final String STATUS_RUNNING = "RUNNING";
    public static final String STATUS_CANCELLING = "CANCELLING";
    public static final String STATUS_CANCELLED = "CANCELLED";
    public static final String STATUS_COMPLETED = "COMPLETED";
    public static final String STATUS_FAILED = "FAILED";

    private String sessionId;
    private String invokeId;
    private String status;
    private long updateTime;

    /** 判断当前状态是否已经不可继续执行。 */
    public boolean isTerminal() {
        return STATUS_CANCELLED.equals(status) || STATUS_COMPLETED.equals(status) || STATUS_FAILED.equals(status);
    }
}
