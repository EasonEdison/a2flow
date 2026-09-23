package dev.a2flow.management.storage.db.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 通用资产成员数据对象。
 *
 * <p>该 DO 对应 {@code skill_asset_principal}，保存不随资产版本变化的负责人关系。发布、回滚、
 * 新建变更和版本复制不得复制或覆盖本表。
 */
@Data
@Accessors(chain = true)
@TableName("skill_asset_principal")
public class SkillAssetPrincipalDO {

    /** 自增主键。 */
    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /** 权限命名空间，一期固定为 SKILL_FACTORY。 */
    @TableField("namespace")
    private String namespace;

    /** 资产类型，复用共享发布资产类型。 */
    @TableField("asset_type")
    private String assetType;

    /** 资产稳定标识。 */
    @TableField("asset_key")
    private String assetKey;

    /** 主体类型，一期固定为 USER。 */
    @TableField("principal_type")
    private String principalType;

    /** 主体稳定标识，一期为英文用户名。 */
    @TableField("principal_id")
    private String principalId;

    /** 成员角色，一期固定为 OWNER。 */
    @TableField("role_type")
    private String roleType;

    /** 关系状态，ACTIVE 或 DISABLED。 */
    @TableField("status")
    private String status;

    /** JSON 扩展属性。 */
    @TableField("attribute")
    private String attribute;

    /** 关系创建人。 */
    @TableField("creator")
    private String creator;

    /** 最近修改人。 */
    @TableField("modifier")
    private String modifier;

    /** 创建时间，毫秒时间戳。 */
    @TableField("create_time")
    private Long createTime;

    /** 更新时间，毫秒时间戳。 */
    @TableField("update_time")
    private Long updateTime;
}
