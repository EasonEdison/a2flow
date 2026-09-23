package dev.a2flow.management.aicoding.validation;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 运行验证报告缓存。
 *
 * <p>该缓存让后续“让主 Agent 修复”可以通过 reportId 读取后端刚生成过的可信 ValidationReport，
 * 而不是只信任前端回传 JSON。当前实现是进程内缓存，后续可替换为 DB/Redis，调用方接口不变。
 */
@Slf4j
@Component
public class SkillFactoryValidationReportStore {

    private final Map<String, ValidationReport> reportMap = new ConcurrentHashMap<>();

    /**
     * 写入运行验证报告。
     */
    public ValidationReport put(ValidationReport report) {
        if (report == null) {
            return null;
        }
        String reportId = StringUtils.defaultIfBlank(report.getReportId(), report.getTaskId());
        if (StringUtils.isBlank(reportId)) {
            return report;
        }
        report.setReportId(reportId);
        reportMap.put(reportId, report);
        log.info("SkillFactory运行验证报告已缓存, reportId={}, workspaceId={}, skillCode={}, status={}",
                reportId, report.getWorkspaceId(), report.getSkillCode(), report.getStatus());
        return report;
    }

    /**
     * 按 reportId 读取运行验证报告。
     */
    public ValidationReport get(String reportId) {
        if (StringUtils.isBlank(reportId)) {
            return null;
        }
        return reportMap.get(reportId);
    }
}
