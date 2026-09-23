package dev.a2flow.management.storage.db.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import dev.a2flow.management.storage.db.entity.SkillFactoryWorkspaceDO;

/**
 * SkillFactory 工作区元数据 Mapper。
 *
 * <p>该 Mapper 只负责连接 `skill_draft` 表里的工作区相关字段，风格对齐 {@link SessionMapper}。
 * 本地 workspace 目录创建、路径校验、文件扫描等文件系统动作不属于 Mapper 职责，应由 Repository/Service 承接。
 */
@Mapper
public interface SkillFactoryWorkspaceMapper extends BaseMapper<SkillFactoryWorkspaceDO> {

}
