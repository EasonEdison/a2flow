package dev.a2flow.management.lifecycle.domain;

import lombok.Data;

/** 列表摘要不携带 Schema、demo、模板或运行配置；编辑必须读取详情。 */
@Data
public class ComponentListItem {
    private Long id;
    private String assetType;
    private String componentName;
    private String componentNameCn;
    private String dslType;
    private Integer protocolVersion;
    private String owner;
    private String scene;
    private boolean enabled;
    private Long updateTime;
}
