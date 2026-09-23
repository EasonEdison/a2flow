package dev.a2flow.management.model;

import java.util.ArrayList;
import java.util.List;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 能力草稿校验结果 DTO。
 *
 * <p>该对象只描述当前草稿的静态结构和发布前缺口，供 M 端校验中心展示。它不发起 KRPC/HTTP
 * dry-run，也不把结构通过错误标记为可执行或已发布；真实执行证据由后续 CapabilityAction
 * 绑定和验证链路补充。
 */
@Data
@Accessors(chain = true)
public class CapabilityActionValidationResult {

    private String draftId;
    private Integer revision;
    private Boolean valid;
    private String status;
    private List<String> errors = new ArrayList<>();
    private List<String> warnings = new ArrayList<>();
    private List<String> publishBlockers = new ArrayList<>();
    private Long validatedAt;
}
