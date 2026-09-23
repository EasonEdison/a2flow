package dev.a2flow.management.model;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 组件预览校验结果。
 *
 * <p>该结果只描述组件中心官方 demo 或用户临时 JSON 是否满足已登记协议。它不触发真实前端渲染、
 * 不保存用户粘贴内容，也不替代 Skill 详情页基于当前 workspace 输出的发布前渲染验收。
 */
@Data
@Accessors(chain = true)
public class SkillFactoryComponentPreviewResult {

    private Boolean valid;
    private Long assetId;
    private String componentName;
    private String assetType;
    private String dslType;
    private String previewJson;
    private Boolean paramsValid;
    private Boolean renderTemplateValid;
    private Boolean actionValid;
    private List<Map<String, Object>> a2uiMessagesPreview = new ArrayList<>();
    private String contextSummaryPreview;
    private List<String> errors = new ArrayList<>();
}
