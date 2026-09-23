package dev.a2flow.management.lifecycle.domain;

import java.util.ArrayList;
import java.util.List;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow keyset 分页响应。
 *
 * <p>items 按 (updateTime,id) 倒序稳定排列，nextPageToken 只编码最后一条数据库游标；空值表示没有
 * 下一页。上游由 WorkflowDefinitionService 组装，下游供控制面 API 使用，不支持 offset。
 */
@Data
@Accessors(chain = true)
public class WorkflowListPageView {

    private List<WorkflowListItemView> items = new ArrayList<>();
    private String nextPageToken;
}
