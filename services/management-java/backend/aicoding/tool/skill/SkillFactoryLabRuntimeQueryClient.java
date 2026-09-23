package dev.a2flow.management.aicoding.tool.skill;

import java.util.Map;

/** Runtime history query port. A real adapter must validate remote errors and return original structured data. */
public interface SkillFactoryLabRuntimeQueryClient {
    Map<String, Object> queryRecentSkillRuns(QueryLabMessageListRequest request);
    Map<String, Object> querySkillRunDetail(QueryLabTraceDetailRequest request);
}
