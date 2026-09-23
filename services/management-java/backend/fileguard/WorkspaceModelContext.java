package dev.a2flow.management.fileguard;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 本轮模型调用使用的 workspace 事实上下文。
 *
 * <p>该对象把一次实时文件快照和由该快照生成的模型上下文绑定在一起，避免重复扫描期间文件发生变化，
 * 导致模型收到的摘要与持久化的“模型已观测快照”不是同一份事实。
 */
@Data
@Accessors(chain = true)
public class WorkspaceModelContext {

    private WorkspaceSnapshot snapshot;
    private String modelContext;
}
