package dev.a2flow.management.lifecycle.domain;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 工作区文件领域对象。
 *
 * <p>文件事实源是受控 workspace 文件系统。本对象只承载一次目录扫描或文件读取的结果，
 * 不映射数据库表，也不承担历史审计和索引缓存职责。
 */
@Data
@Accessors(chain = true)
public class SkillWorkspaceFile {

    private String filePath;
    private String fileName;
    private String fileType;
    private Long fileSize;
    private String contentDigest;
    private Long modifyTime;
    private String content;
}
