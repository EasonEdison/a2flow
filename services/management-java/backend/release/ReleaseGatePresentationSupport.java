package dev.a2flow.management.release;

import java.util.List;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.release.ReleaseModels.GateResult;

/** 发布检查摘要和阻塞原因展示；不参与门禁决策。 */
final class ReleaseGatePresentationSupport {
    private ReleaseGatePresentationSupport() {
    }

    /** 保留审批和发布记录使用的检查状态摘要。 */
    static String gateSummary(List<GateResult> gates) {
        if (gates == null || gates.isEmpty()) {
            return "无发布门禁";
        }
        return String.join("；", gates.stream()
                .map(gate -> String.format("%s:%s%s",
                        gate.getLabel(), gate.getStatus(), gate.getRequired() ? "(必选)" : ""))
                .toList());
    }

    /** 返回失败检查的具体原因，供发布按钮和页面共同解释阻塞。 */
    static String requiredGateFailureMessage(String environment, List<GateResult> gates) {
        return environment + "发布未通过：" + gates.stream()
                .filter(gate -> Boolean.TRUE.equals(gate.getRequired())
                        && !StringUtils.equals(gate.getStatus(), "PASSED"))
                .map(gate -> gate.getLabel() + "：" + gate.getMessage())
                .collect(Collectors.joining("；"));
    }

}
