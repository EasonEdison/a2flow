package dev.a2flow.management.agentcore.runtime.prompt;

import java.util.List;

import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.agentcore.runtime.skill.SkillMetadata;

/**
 * SkillFactory 本地提示词片段构造器。
 *
 * <p>迁移到 sellerdata 后，AI Coding 只需要复用通用 `<available_skills>` 协议来告诉模型当前 Agent
 * 挂载了哪些可选 Skill。该类不再承接原 agent-service 的主从 Agent 路由、灰度提示词或历史路由记忆。
 */
@Component
public class PromptManager {

    /**
     * 构建可挂载 Skill 的模型提示词。
     */
    public String buildSkillPrompt(List<SkillMetadata> enabledSkills) {
        StringBuilder sb = new StringBuilder();
        sb.append("## Skills (mandatory):\n");
        sb.append("Before replying: scan <available_skills> name and description entries.\n");
        sb.append("Constraints: never read more than one skill up front; only read after selecting.\n");
        sb.append("- If exactly one skill clearly applies: call use_skill with its exact skillCode. "
                + "The tool returns the full SKILL.md, latest formal version, absolute package root and file tree. "
                + "Follow the returned SKILL.md. Do not read or "
                + "execute other files or scripts that are not within this scope.\n");
        sb.append("- If multiple could apply: choose the most specific one, then activate/follow it.\n");
        sb.append("- If there is no clear application or no skills exist: Do not retrieve, find, read or execute other "
                + "files or scripts.\n");
        sb.append("Never call read on a directory. Use tree for directories. After use_skill succeeds, use read for "
                + "an exact absolute support-file path and python for an exact absolute script path returned under "
                + "skillDirectory. Never guess a mounted Skill path inside the current editing workspace, and never "
                + "persist runtime absolute paths into generated Skill files.\n");
        sb.append("<available_skills>\n");
        if (CollectionUtils.isNotEmpty(enabledSkills)) {
            for (SkillMetadata skill : enabledSkills) {
                sb.append("<skill>\n");
                sb.append("<name>").append(skill.getName()).append("</name>");
                if (StringUtils.isNotBlank(skill.getDescription())) {
                    sb.append("<description>").append(skill.getDescription()).append("</description>");
                }
                sb.append("</skill>\n");
            }
        }
        sb.append("</available_skills>\n");
        return sb.toString();
    }
}
