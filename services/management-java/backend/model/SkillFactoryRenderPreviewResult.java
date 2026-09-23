package dev.a2flow.management.model;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 运行态渲染预览结果。
 *
 * <p>该 DTO 是 sellerdata 的 M 端预览 method 返回形态，和 adviser 真实运行态渲染结果保持字段对齐。
 * 它只表达协议校验和 A2UI/CARD_CONTAINER payload，不保存用户粘贴内容，也不执行
 * Java/Groovy/JavaScript 等页面上传代码。
 */
@Data
@Accessors(chain = true)
public class SkillFactoryRenderPreviewResult {

    private Boolean valid;
    private Long assetId;
    private String assetType;
    private String componentName;
    private String componentNameCn;
    private String renderProtocol;
    private Integer protocolVersion;
    private String bundleUrl;
    private String dslType;
    private String agentUiDsl;
    private Boolean paramsValid;
    private Object data;
    private List<Map<String, Object>> messages = new ArrayList<>();
    private List<String> errors = new ArrayList<>();
}
