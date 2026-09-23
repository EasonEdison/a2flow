package dev.a2flow.management.access;

import java.util.ArrayList;
import java.util.List;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 通用资产访问结果。
 *
 * <p>前端使用该结果渲染只读态；后端仍会在每次修改请求中重新鉴权，不能把前端缓存当作授权凭证。
 */
@Data
@Accessors(chain = true)
public class AssetAccessResult {

    private String assetType;
    private String assetKey;
    private List<AssetPrincipal> owners = new ArrayList<>();
    private String role;
    private AssetPermissions permissions;
    private String reason;
}
