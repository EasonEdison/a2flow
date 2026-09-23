package dev.a2flow.management.model;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 能力中心可编辑草稿 DTO。
 *
 * <p>该对象是能力注册/编辑页和 Repository 之间的 canonical draft。上游是统一 SkillFactory
 * method 分发和后续 AI Authoring 快照/增量事件，下游是草稿 Repository；它不代表已发布的
 * CapabilityActionVersion，不提供运行时 Tool，也不保存浏览器 Cookie、token 或任意 HTTP 凭证。
 */
@Data
@Accessors(chain = true)
public class CapabilityActionDraft {

    private String draftId;
    private Integer revision;
    private String status;
    private Map<String, Object> draft = new LinkedHashMap<>();
    private List<String> validationErrors;
    private List<String> validationWarnings;
    private String validationStatus;
    private Boolean published;
    private Integer publishedVersion;
    private String businessDomain;
    private String businessDomainName;
    private String capabilityDomain;
    private String capabilityDomainName;
    private String specialistId;
    private String specialistName;
    private Boolean editing;
    private Boolean online;
    private AssetReleaseEnvironmentFacts releaseEnvironmentFacts;
    private String creator;
    private String modifier;
    private Long createTime;
    private Long updateTime;
}
