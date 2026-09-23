package dev.a2flow.management.storage.db.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 通用实体关系数据对象。
 *
 * <p>该 DO 对应 `entity_relation`，使用源实体稳定 ID 和源版本保存跨中心关系。一期由 Skill 工作台
 * 写入 Skill 到专员、业务能力、直接组件等关系；上游 Service 负责解析目标事实和生成受控快照，
 * 下游 Mapper/Repository 负责完整集合的查询、覆盖和版本复制。本类不维护独立关系版本、关系头指针
 * 或业务状态机，Skill 关系版本直接等于 `skill_draft.version`。
 */
@Data
@Accessors(chain = true)
@TableName("entity_relation")
public class EntityRelationDO {

    /** 关系主键。 */
    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /** 关系命名空间。 */
    @TableField("namespace")
    private String namespace;

    /** 源实体类型。 */
    @TableField("source_entity_type")
    private String sourceEntityType;

    /** 源实体稳定 ID。 */
    @TableField("source_entity_id")
    private String sourceEntityId;

    /** 源实体数字版本，一期直接使用 Skill 数字版本。 */
    @TableField("source_version")
    private Integer sourceVersion;

    /** 关系类型。 */
    @TableField("relation_type")
    private String relationType;

    /** 目标实体类型。 */
    @TableField("target_entity_type")
    private String targetEntityType;

    /** 目标实体稳定 ID。 */
    @TableField("target_entity_id")
    private String targetEntityId;

    /** 目标实体稳定业务 code。 */
    @TableField("target_entity_code")
    private String targetEntityCode;

    /** 目标实体版本，例如能力 revision 或组件 version。 */
    @TableField("target_version")
    private String targetVersion;

    /** 关系模式，例如执行、不渲染或直接组件引用。 */
    @TableField("relation_mode")
    private String relationMode;

    /** 服务端生成的受控关系快照 JSON。 */
    @TableField("snapshot_json")
    private String snapshotJson;

    /** 当前关系集合内的稳定顺序。 */
    @TableField("sort_no")
    private Integer sortNo;

    /** JSON 扩展属性，不承载固定关系字段。 */
    @TableField("attribute")
    private String attribute;

    /** 最近操作人。 */
    @TableField("operator")
    private String operator;

    /** 创建时间，毫秒时间戳。 */
    @TableField("create_time")
    private Long createTime;

    /** 更新时间，毫秒时间戳。 */
    @TableField("update_time")
    private Long updateTime;
}
