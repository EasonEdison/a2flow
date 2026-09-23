package dev.a2flow.management.agentcore.runtime.skill;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Data;

/**

 * Created on 2026-04-23
 */
@Data
@JsonInclude(JsonInclude.Include.NON_NULL)
public class SkillMetadata {
    /**
     * skill name (唯一)
     */
    private String name;

    /**
     * Semantic version (e.g., 1.0.0)
     */
    private String version;

    /**
     * 意图描述
     */
    private String description;

    /**
     * 存储path of the skill
     */
    private String location;

    /**
     * 引用或依赖的skill name
     */
    private List<String> dependencies;
    /**
     * skill 启用状态
     */
    private boolean enabled;

    @JsonIgnore
    private String content;

    private Long createdAt;

    private Long updatedAt;
}
