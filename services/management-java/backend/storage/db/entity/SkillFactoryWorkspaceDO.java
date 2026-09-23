package dev.a2flow.management.storage.db.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 工作区数据对象。
 *
 * <p>该 DO 只对应 `skill_draft` 草稿主表，保存 Skill 稳定身份、当前编辑版本和 workspace 摘要。
 * 发布版本、环境指针和 ZIP 产物统一由共享发布控制面的 `skill_asset_release_state` 管理；
 * 工作区文件正文和目录扫描结果不写入本对象。
 */
@Data
@Accessors(chain = true)
@TableName("skill_draft")
public class SkillFactoryWorkspaceDO {

    /**
     * 草稿主键。
     */
    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /**
     * Skill 英文唯一标识。
     */
    @TableField("skill_code")
    private String skillCode;

    /**
     * Skill 中文名称。
     */
    @TableField("skill_name_cn")
    private String skillNameCn;

    /**
     * Skill 英文名称。
     */
    @TableField("skill_name_en")
    private String skillNameEn;

    /**
     * Skill 能力描述，用于 M 端列表、详情和后续对话上下文识别 Skill 边界。
     */
    @TableField("skill_description")
    private String skillDescription;

    /**
     * 业务场域，用于区分直播经营、内容经营等 Skill 适用业务范围。
     */
    @TableField("business_domain")
    private String businessDomain;

    /**
     * 能力域，用于区分计划创建、复盘诊断等 Skill 核心能力分类。
     */
    @TableField("capability_domain")
    private String capabilityDomain;

    /**
     * 创建来源，例如 CHAT_CREATE、ZIP_IMPORT、PACKAGE_RESTORE、GIT_IMPORT。
     */
    @TableField("create_source")
    private String createSource;

    /**
     * 文件工作区 ID，sellerdata lifecycle 使用该值拼接受控本地目录。
     */
    @TableField("workspace_id")
    private String workspaceId;

    /**
     * 当前工作区相对路径。
     */
    @TableField("workspace_path")
    private String workspacePath;

    /**
     * 最近持久化的文件树摘要，仅用于页面和列表缓存。
     */
    @TableField("file_tree_digest")
    private String fileTreeDigest;

    /**
     * ZIP 导入时的原始包地址，非导入场景为空。
     */
    @TableField("source_zip_url")
    private String sourceZipUrl;

    /**
     * 当前编辑版本号，例如 1、2。
     */
    @TableField("version")
    private Integer version;

    /**
     * LangBridge Skill 稳定 ID。
     *
     * <p>首次外部发布创建成功后回写，后续预发、线上与历史重发均复用该 ID；它属于 Skill 主记录，
     * 不随 SkillFactory 数字版本变化。
     */
    @TableField("lang_bridge_skill_id")
    private Long langBridgeSkillId;

    /**
     * 草稿生命周期状态。
     */
    @TableField("status")
    private String status;

    /**
     * 主负责人。
     */
    @TableField("owner")
    private String owner;

    /**
     * 创建人。
     */
    @TableField("creator")
    private String creator;

    /**
     * 最近修改人。
     */
    @TableField("modifier")
    private String modifier;

    /**
     * 扩展摘要 JSON。
     */
    @TableField("ext_json")
    private String extJson;

    /**
     * 扩展属性 JSON，用于后续灰度字段或非核心结构化信息扩展。
     */
    @TableField("attribute")
    private String attribute;

    /**
     * 逻辑删除标记。
     */
    @TableField("deleted")
    private Integer deleted;

    /**
     * 创建时间，毫秒时间戳。
     */
    @TableField("create_time")
    private Long createTime;

    /**
     * 更新时间，毫秒时间戳。
     */
    @TableField("update_time")
    private Long updateTime;
}
