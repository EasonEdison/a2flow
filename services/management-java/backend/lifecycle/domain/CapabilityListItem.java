package dev.a2flow.management.lifecycle.domain;

/** 能力管理列表摘要；编辑合同由详情接口读取。 */
public record CapabilityListItem(String draftId, String actionCode, String nameCn,
        String description, String sourceType, String sideEffectLevel,
        String businessDomain, String businessDomainName,
        String capabilityDomain, String capabilityDomainName,
        String specialistId, String specialistName, boolean editing, boolean online,
        long updateTime) { }
