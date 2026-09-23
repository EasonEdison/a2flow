package dev.a2flow.management.lifecycle.domain;

import java.util.ArrayList;
import java.util.List;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory Skill 草稿领域对象。
 *
 * <p>该对象承载 Skill 的稳定身份、当前编辑版本和工作区运行态摘要，不绑定数据库注解。
 * Repository 负责在本对象与 `skill_draft` 数据对象之间转换，应用服务不得直接依赖持久化 DO。
 */
@Data
@Accessors(chain = true)
public class SkillDraft {

    private Long id;
    private String skillCode;
    private String skillNameCn;
    private String skillNameEn;
    private String skillDescription;
    private String businessDomain;
    private String capabilityDomain;
    private String createSource;
    private String workspaceId;
    private String workspaceRoot;
    private String workspacePath;
    private String fileTreeDigest;
    private String sourceZipUrl;
    private Integer version;
    private Long langBridgeSkillId;
    private String status;
    private String owner;
    private String creator;
    private String modifier;
    private String extJson;
    private String attribute;
    private Integer fileCount;
    private List<SkillWorkspaceFile> files = new ArrayList<>();
    private Long createTime;
    private Long updateTime;
}
