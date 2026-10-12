package dev.a2flow.management.lifecycle.domain;

import java.util.Map;

/** Application list summary; templates and bindings stay on the detail endpoint. */
public record ApplicationListItem(String id, String appCode, String nameCn, String description,
        String interactionMode, String protocolVersion, String protocolStatus,
        Map<String, Object> catalog, String status, Map<String, Object> releases,
        Boolean hasUnpublishedChanges, String sourceDigest, int showComponentCount,
        int actionBindingCount, long createTime, long updateTime) { }
