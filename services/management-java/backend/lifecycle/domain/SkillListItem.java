package dev.a2flow.management.lifecycle.domain;

import lombok.Data;

/** 首屏列表投影，不携带工作区文件、历史版本或完整发布快照。 */
@Data
public class SkillListItem {
    private String skillCode;
    private String skillNameCn;
    private String skillNameEn;
    private String skillDescription;
    private String businessDomain;
    private String capabilityDomain;
    private String workspaceId;
    private String specialistId;
    private String specialistName;
    private String owner;
    private String creator;
    private Integer version;
    private String versionStatus;
    private String draftStatus;
    private String onlineVersionId;
    private String preprodVersionId;
    private Long createTime;
    private Long updateTime;

    public String getVersionLabel() {
        return "v" + version;
    }

    public boolean isEditable() {
        return "EDITING".equals(draftStatus);
    }
}
