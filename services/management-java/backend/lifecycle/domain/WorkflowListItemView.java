package dev.a2flow.management.lifecycle.domain;

import java.util.LinkedHashMap;
import java.util.Map;

import dev.a2flow.management.release.ReleaseModels.EnvironmentState;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 列表单项视图。
 *
 * <p>定义字段来自 workflow_definition，环境字段来自 common-v2 ReleaseOverview 的 PRT/ONLINE
 * 稳定指针。该模型不读取运行态、不推断 latest，也不把缺失环境指针补成虚假版本。
 */
@Data
@Accessors(chain = true)
public class WorkflowListItemView {

    private WorkflowDefinitionView workflow;
    private Map<String, EnvironmentState> environmentPointers = new LinkedHashMap<>();
}
