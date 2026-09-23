package dev.a2flow.management.storage.db.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 共享发布聚合数据对象。
 *
 * <p>一行保存一个 `assetType + assetKey` 的发布治理聚合，正文以 stateJson 存储，revision 用于正式
 * DB 路径的乐观锁。领域正文仍保存在各自事实源，本表只保存 Change/Build/Version/Deployment 快照。
 */
@Data
@Accessors(chain = true)
@TableName("skill_asset_release_state")
public class AssetReleaseStateDO {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("asset_type")
    private String assetType;

    @TableField("asset_key")
    private String assetKey;

    @TableField("revision")
    private Integer revision;

    @TableField("state_json")
    private String stateJson;

    @TableField("attribute")
    private String attribute;

    @TableField("deleted")
    private Integer deleted;

    @TableField("create_time")
    private Long createTime;

    @TableField("update_time")
    private Long updateTime;
}
