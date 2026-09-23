package dev.a2flow.management.lifecycle.domain.graph;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 最终结论下方的一条处理建议配置。
 *
 * <p>上游由 M 端在 {@code summaryConfig.handlingSuggestions} 中配置，并由
 * {@link WorkflowGraphAggregateParser} 严格解析；下游随 Workflow 发布正文不可变冻结，供 Adviser
 * 从当前 Run 的冻结快照生成 {@code ActionAdvice}。本类只承载展示与发送消息所需的字面量，不承载
 * 动态脚本、服务端动作绑定或运行态状态。
 */
@Data
@Accessors(chain = true)
@JsonInclude(JsonInclude.Include.NON_NULL)
public class WorkflowHandlingSuggestion {

    private String suggestionId;
    private String iconUrl;
    private String displayText;
    private String sendMessageText;
}
