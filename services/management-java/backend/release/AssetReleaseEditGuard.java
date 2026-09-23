package dev.a2flow.management.release;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.ReleaseModels.ReleaseChange;
import dev.a2flow.management.storage.db.repository.AssetReleaseStateRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 资产编辑门禁。
 *
 * <p>该类统一约束 Skill、渲染组件和业务能力的编辑入口：新注册且尚无正式版本的资产允许完成
 * 初始版本；已有正式版本后，只有共享发布控制面存在 ACTIVE 变更时才允许修改领域事实源。
 */
@Component
@Slf4j
public class AssetReleaseEditGuard {

    private static final String STATUS_ACTIVE = "ACTIVE";
    private static final String ERROR_EDITABLE_CHANGE_REQUIRED = "当前资产没有可编辑变更，请先新建变更";

    @Resource
    private AssetReleaseStateRepository stateRepository;

    /**
     * 校验资产当前是否允许写入。
     *
     * @param assetType 资产类型
     * @param assetKey 资产稳定标识
     * @param action 当前写操作名称，仅用于安全审计日志
     * @param operator 操作人
     */
    public void requireEditableChange(ReleaseAssetType assetType, String assetKey,
            String action, String operator) {
        AssetReleaseState state = stateRepository.find(assetType, assetKey);
        ReleaseChange activeChange = state.getActiveChange();
        boolean initialEditable = state.getVersions().isEmpty()
                && (activeChange == null || StringUtils.equals(activeChange.getStatus(), STATUS_ACTIVE));
        boolean activeEditable = activeChange != null
                && StringUtils.equals(activeChange.getStatus(), STATUS_ACTIVE);
        if (initialEditable || activeEditable) {
            log.info("共享资产编辑门禁通过, assetType:{}, assetKey:{}, action:{}, operator:{}, initialEditable:{}",
                    assetType, assetKey, action, operator, initialEditable);
            return;
        }
        log.warn("共享资产编辑门禁拒绝写入, assetType:{}, assetKey:{}, action:{}, operator:{}, "
                        + "activeChangeStatus:{}, formalVersionCount:{}",
                assetType, assetKey, action, operator,
                activeChange == null ? null : activeChange.getStatus(), state.getVersions().size());
        throw new IllegalStateException(ERROR_EDITABLE_CHANGE_REQUIRED);
    }
}
