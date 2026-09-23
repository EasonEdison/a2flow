package dev.a2flow.management.access;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.storage.db.entity.SkillAssetPrincipalDO;
import dev.a2flow.management.storage.db.repository.CapabilityActionDraftRepository;
import dev.a2flow.management.storage.db.repository.SkillAssetPrincipalRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceRepository;
import dev.a2flow.management.storage.db.repository.WorkflowDefinitionRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 通用资产授权 Service。
 *
 * <p>该类把资产负责人表、管理员 KConf 和固定动作矩阵组合成唯一授权结论。上游 method dispatcher、
 * 发布控制面和关键领域 Service 只调用本类，不得再读取领域 owner 字符串；前端使用
 * {@link #getAccess(String, ReleaseAssetType, String)} 返回的权限投影渲染只读态。
 */
@Service
@Slf4j
public class AssetAuthorizationService {

    private static final String ERROR_CODE_PERMISSION_DENIED = "ASSET_PERMISSION_DENIED";
    private static final String ERROR_PREFIX = "[ASSET_PERMISSION_DENIED] ";
    private static final String ERROR_OPERATOR_REQUIRED = "operator is required";
    private static final String ERROR_OWNERS_JSON_INVALID = "ownersJson must be a JSON string array";
    private static final String VIEWER_REASON = "当前用户不是资产负责人，仅可查看";
    private static final String ASSET_TYPE_A2UI_ATOM = "A2UI_ATOM";
    private static final String ASSET_TYPE_A2UI_CATALOG = "A2UI_CATALOG";
    private static final String ASSET_TYPE_A2UI_APPLICATION = "A2UI_APPLICATION";

    @Resource
    private SkillAssetPrincipalRepository skillAssetPrincipalRepository;

    @Resource
    private SkillFactoryWorkspaceRepository skillFactoryWorkspaceRepository;

    @Resource
    private SkillFactoryComponentAssetRepository skillFactoryComponentAssetRepository;

    @Resource
    private CapabilityActionDraftRepository capabilityActionDraftRepository;

    @Resource
    private WorkflowDefinitionRepository workflowDefinitionRepository;

    @Resource
    private ManagementIdentityProvider managementIdentityProvider;

    /**
     * 查询当前操作者对指定资产的角色和动作权限。
     */
    public AssetAccessResult getAccess(String operator, ReleaseAssetType assetType, String assetKey) {
        requireOperator(operator);
        requireAssetExists(assetType, assetKey);
        boolean admin = isAdmin(operator);
        boolean owner = skillAssetPrincipalRepository.isActiveOwner(assetType, assetKey, operator);
        AssetAccessRole role = admin ? AssetAccessRole.ADMIN
                                     : owner ? AssetAccessRole.OWNER : AssetAccessRole.VIEWER;
        List<AssetPrincipal> owners = skillAssetPrincipalRepository.listActiveOwners(assetType, assetKey)
                .stream()
                .map(this::toPrincipal)
                .toList();
        AssetAccessResult result = new AssetAccessResult()
                .setAssetType(assetType.name())
                .setAssetKey(assetKey)
                .setOwners(owners)
                .setRole(role.name())
                .setPermissions(permissions(role))
                .setReason(role == AssetAccessRole.VIEWER ? VIEWER_REASON : StringUtils.EMPTY);
        log.info("SkillFactory资产权限查询完成, operator:{}, assetType:{}, assetKey:{}, role:{}, ownerCount:{}",
                operator, assetType, assetKey, role, owners.size());
        return result;
    }

    /**
     * 校验当前操作者是否允许执行指定动作。
     */
    public void requirePermission(String operator, ReleaseAssetType assetType,
            String assetKey, AssetAction action) {
        AssetAccessResult access = getAccess(operator, assetType, assetKey);
        if (allowed(access.getPermissions(), action)) {
            return;
        }
        log.warn("SkillFactory拒绝未授权资产操作, operator:{}, assetType:{}, assetKey:{}, action:{}, role:{}",
                operator, assetType, assetKey, action, access.getRole());
        throw permissionDenied(
                assetType, assetKey, action,
                ERROR_PREFIX + "当前用户无权执行该资产操作: " + action.name());
    }

    /**
     * 资产创建完成后初始化负责人。
     *
     * <p>未传 ownersJson 时负责人默认为当前可信 operator；普通创建人必须包含在负责人集合中，
     * 管理员可以代其他用户创建资产。
     */
    public AssetAccessResult initializeOwners(String operator, ReleaseAssetType assetType,
            String assetKey, String ownersJson) {
        List<String> owners = validateCreationOwners(operator, assetType, assetKey, ownersJson);
        skillAssetPrincipalRepository.replaceOwners(assetType, assetKey, owners, operator);
        log.info("SkillFactory初始化资产负责人完成, operator:{}, assetType:{}, assetKey:{}, ownerCount:{}",
                operator, assetType, assetKey, owners.size());
        return getAccess(operator, assetType, assetKey);
    }

    /**
     * 在创建资产或准备工作区文件前校验初始负责人集合。
     *
     * <p>该方法不写数据库，只负责可信 operator、负责人参数和普通创建人必须在负责人集合内的规则。
     * 真正的领域记录与负责人写入仍由短事务编排服务完成。
     */
    public List<String> validateCreationOwners(String operator, ReleaseAssetType assetType,
            String assetKey, String ownersJson) {
        requireOperator(operator);
        if (!isAdmin(operator)) {
            throw permissionDenied(assetType, assetKey, AssetAction.EDIT, "ADMIN_REQUIRED");
        }
        List<String> owners = parseOwners(ownersJson, operator);
        log.info("SkillFactory初始负责人集合校验通过, operator:{}, assetType:{}, assetKey:{}, ownerCount:{}",
                operator, assetType, assetKey, owners.size());
        return owners;
    }

    /**
     * 管理员完整替换资产负责人。
     */
    public AssetAccessResult replaceOwners(String operator, ReleaseAssetType assetType,
            String assetKey, String ownersJson) {
        requirePermission(operator, assetType, assetKey, AssetAction.MANAGE_OWNER);
        List<String> owners = parseOwners(ownersJson, null);
        skillAssetPrincipalRepository.replaceOwners(assetType, assetKey, owners, operator);
        log.info("SkillFactory管理员替换资产负责人完成, operator:{}, assetType:{}, assetKey:{}, ownerCount:{}",
                operator, assetType, assetKey, owners.size());
        return getAccess(operator, assetType, assetKey);
    }

    /**
     * 统一使用账号会话中的 userId 与管理员角色，不另维护用户名白名单。
     */
    public boolean isAdmin(String operator) {
        if (StringUtils.isBlank(operator)) {
            return false;
        }
        return operator.equals(Long.toString(managementIdentityProvider.userId()))
                && managementIdentityProvider.isAdministrator();
    }

    private List<String> parseOwners(String ownersJson, String defaultOwner) {
        if (StringUtils.isBlank(ownersJson)) {
            if (StringUtils.isBlank(defaultOwner)) {
                throw new IllegalArgumentException(ERROR_OWNERS_JSON_INVALID);
            }
            return List.of(defaultOwner);
        }
        try {
            String[] parsed = JsonSupport.fromJSON(ownersJson, String[].class);
            Set<String> owners = new LinkedHashSet<>();
            if (parsed != null) {
                Arrays.stream(parsed)
                        .map(StringUtils::trimToEmpty)
                        .filter(StringUtils::isNotBlank)
                        .forEach(owners::add);
            }
            if (owners.isEmpty()) {
                throw new IllegalArgumentException(ERROR_OWNERS_JSON_INVALID);
            }
            return new ArrayList<>(owners);
        } catch (RuntimeException e) {
            log.warn("SkillFactory负责人参数解析失败, error:{}", e.getMessage());
            throw new IllegalArgumentException(ERROR_OWNERS_JSON_INVALID);
        }
    }

    private AssetPermissions permissions(AssetAccessRole role) {
        boolean editable = role == AssetAccessRole.ADMIN;
        return new AssetPermissions()
                .setCanView(true)
                .setCanEdit(editable)
                .setCanPublish(editable)
                .setCanForcePublish(role == AssetAccessRole.ADMIN)
                .setCanOffline(editable)
                .setCanManageOwner(role == AssetAccessRole.ADMIN);
    }

    private boolean allowed(AssetPermissions permissions, AssetAction action) {
        return switch (action) {
            case VIEW -> permissions.isCanView();
            case EDIT -> permissions.isCanEdit();
            case PUBLISH -> permissions.isCanPublish();
            case FORCE_PUBLISH -> permissions.isCanForcePublish();
            case OFFLINE -> permissions.isCanOffline();
            case MANAGE_OWNER -> permissions.isCanManageOwner();
        };
    }

    private void requireAssetExists(ReleaseAssetType assetType, String assetKey) {
        boolean exists = switch (assetType) {
            case SKILL -> skillFactoryWorkspaceRepository.findDraftBySkillCode(assetKey) != null;
            case COMPONENT -> componentExists(assetKey);
            case CAPABILITY_ACTION -> capabilityActionDraftRepository.find(assetKey) != null;
            // 编排资产通过 workflow_definition 表检查稳定 workflowCode 是否存在。
            case ORCHESTRATION_CONFIG -> workflowDefinitionRepository.findByWorkflowCode(assetKey) != null;
            case A2UI_ATOM -> skillFactoryComponentAssetRepository.findByAssetTypeAndName(
                    ASSET_TYPE_A2UI_ATOM, assetKey) != null;
            case A2UI_CATALOG -> skillFactoryComponentAssetRepository.findByAssetTypeAndName(
                    ASSET_TYPE_A2UI_CATALOG, assetKey) != null;
            case A2UI_APPLICATION -> skillFactoryComponentAssetRepository.findByAssetTypeAndName(
                    ASSET_TYPE_A2UI_APPLICATION, assetKey) != null;
        };
        if (!exists) {
            log.warn("SkillFactory权限查询资产不存在, assetType:{}, assetKey:{}", assetType, assetKey);
            throw new AssetNotFoundException(assetType, assetKey);
        }
    }

    private boolean componentExists(String assetKey) {
        try {
            return skillFactoryComponentAssetRepository.get(Long.parseLong(assetKey)) != null;
        } catch (NumberFormatException e) {
            return false;
        }
    }

    private AssetPrincipal toPrincipal(SkillAssetPrincipalDO principalDO) {
        return new AssetPrincipal()
                .setPrincipalType(principalDO.getPrincipalType())
                .setPrincipalId(principalDO.getPrincipalId())
                .setRoleType(principalDO.getRoleType());
    }

    private AssetPermissionDeniedException permissionDenied(ReleaseAssetType assetType,
            String assetKey, AssetAction action, String message) {
        return new AssetPermissionDeniedException(message, ERROR_CODE_PERMISSION_DENIED,
                assetType.name(), assetKey, action.name());
    }

    private void requireOperator(String operator) {
        if (StringUtils.isBlank(operator)) {
            throw new IllegalArgumentException(ERROR_OPERATOR_REQUIRED);
        }
        if (!operator.equals(Long.toString(managementIdentityProvider.userId()))) {
            throw new SecurityException("OPERATOR_IDENTITY_MISMATCH");
        }
    }

    /**
     * 校验 operator 是可信入口提供的非空身份，防止匿名调用只读列表接口。
     *
     * <p>委托现有 {@link #requireOperator} 实现；上游调用方通过本方法明确表达
     * "我已确认 operator 来自可信来源"的语义，避免误把匿名或空字符串当合法调用方。
     *
     * @param operator 操作者 userName
     * @throws IllegalArgumentException operator 为空时抛出
     */
    public void requireTrustedOperator(String operator) {
        requireOperator(operator);
    }
}
