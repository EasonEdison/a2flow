package dev.a2flow.management.storage.db.repository;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;
import java.util.function.Supplier;

import jakarta.annotation.Resource;

import org.springframework.stereotype.Repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.storage.db.entity.AssetReleaseStateDO;
import dev.a2flow.management.storage.db.mapper.AssetReleaseStateMapper;
import dev.a2flow.management.storage.db.mapper.SkillFactoryMapperConstants;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 共享发布状态 Repository。
 *
 * <p>该类是发布治理状态唯一持久化边界，使用 Mapper 和 revision 乐观锁读写
 * `skill_asset_release_state`。进程内锁只用于减少同一实例内的重复并发，跨实例一致性由数据库
 * revision 条件保证。
 */
@Repository
@Slf4j
public class AssetReleaseStateRepository {

    private static final int NOT_DELETED = 0;
    private static final int INITIAL_REVISION = 0;
    private static final int ASSET_SCAN_PAGE_SIZE = 100;
    private static final String KEY_SEPARATOR = "::";
    private static final String ERROR_REVISION_CONFLICT = "asset release state revision conflict";
    private static final String READ_LIMIT = "LIMIT 1";
    private static final String WRITE_LOCK_LIMIT = "LIMIT 1 FOR UPDATE";

    private static final Map<String, Object> ASSET_LOCKS = new ConcurrentHashMap<>();

    @Resource
    private AssetReleaseStateMapper assetReleaseStateMapper;

    @Resource
    private AssetReleaseRecordStore recordStore;

    /**
     * 在单资产互斥区内执行完整状态迁移，避免同一实例内重复点击产生并发流水。
     */
    public <T> T executeLocked(ReleaseAssetType assetType, String assetKey, Supplier<T> operation) {
        Object lock = ASSET_LOCKS.computeIfAbsent(storageKey(assetType.name(), assetKey), ignored -> new Object());
        synchronized (lock) {
            return operation.get();
        }
    }

    /** 查询资产发布聚合；不存在时返回 revision=0 的空聚合。 */
    public AssetReleaseState find(ReleaseAssetType assetType, String assetKey) {
        AssetReleaseStateDO stateDO = findDb(assetType.name(), assetKey);
        if (stateDO == null) {
            return new AssetReleaseState()
                    .setAssetType(assetType.name())
                    .setAssetKey(assetKey)
                    .setRevision(INITIAL_REVISION);
        }
        return toState(stateDO);
    }

    /** 查询某类资产全部发布聚合，供 ONLINE 正式快照只读查询使用。 */
    public List<AssetReleaseState> listByAssetType(ReleaseAssetType assetType) {
        return assetReleaseStateMapper.selectList(new LambdaQueryWrapper<AssetReleaseStateDO>()
                        .eq(AssetReleaseStateDO::getAssetType, assetType.name())
                        .eq(AssetReleaseStateDO::getDeleted, NOT_DELETED)
                        .orderByAsc(AssetReleaseStateDO::getAssetKey))
                .stream()
                .map(this::toState)
                .toList();
    }

    /**
     * 按稳定 assetKey 有界扫描并逐个消费发布聚合，避免列表调用方持有全部历史快照。
     * 每页使用 keyset 和 MyBatis 分页插件，不做 count；跨页继续扫描直到读尽，不截断合法资产。
     */
    public void scanByAssetType(ReleaseAssetType assetType, Consumer<AssetReleaseState> consumer) {
        String cursor = null;
        int scannedCount = 0;
        while (true) {
            LambdaQueryWrapper<AssetReleaseStateDO> wrapper = new LambdaQueryWrapper<AssetReleaseStateDO>()
                    .eq(AssetReleaseStateDO::getAssetType, assetType.name())
                    .eq(AssetReleaseStateDO::getDeleted, NOT_DELETED)
                    .gt(cursor != null, AssetReleaseStateDO::getAssetKey, cursor)
                    .orderByAsc(AssetReleaseStateDO::getAssetKey);
            List<AssetReleaseStateDO> page = assetReleaseStateMapper.selectPage(
                    new Page<AssetReleaseStateDO>(1, ASSET_SCAN_PAGE_SIZE, false), wrapper).getRecords();
            for (AssetReleaseStateDO row : page) {
                consumer.accept(toState(row));
            }
            scannedCount += page.size();
            if (page.size() < ASSET_SCAN_PAGE_SIZE) {
                break;
            }
            cursor = page.get(page.size() - 1).getAssetKey();
        }
        log.info("共享发布聚合分页扫描完成, assetType:{}, scannedCount:{}", assetType, scannedCount);
    }

    /** 按 expectedRevision 原子保存新独立记录与根引用；CAS 失败回滚子行写入。 */
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public AssetReleaseState save(AssetReleaseState state, int expectedRevision) {
        return saveDb(state, expectedRevision);
    }

    private AssetReleaseStateDO findDb(String assetType, String assetKey) {
        return findDb(assetType, assetKey, false);
    }

    /** 写事务读取并锁定当前根行，避免使用旧快照构造新引用；普通查询不加锁。 */
    private AssetReleaseStateDO findDb(String assetType, String assetKey, boolean lockForUpdate) {
        return assetReleaseStateMapper.selectOne(new LambdaQueryWrapper<AssetReleaseStateDO>()
                .eq(AssetReleaseStateDO::getAssetType, assetType)
                .eq(AssetReleaseStateDO::getAssetKey, assetKey)
                .eq(AssetReleaseStateDO::getDeleted, NOT_DELETED)
                .last(lockForUpdate ? WRITE_LOCK_LIMIT : READ_LIMIT));
    }

    private AssetReleaseState saveDb(AssetReleaseState state, int expectedRevision) {
        AssetReleaseStateDO current = findDb(state.getAssetType(), state.getAssetKey(), true);
        long now = System.currentTimeMillis();
        if (current == null) {
            if (expectedRevision != INITIAL_REVISION) {
                throw new IllegalStateException(ERROR_REVISION_CONFLICT);
            }
            AssetReleaseStateDO inserted = toDO(state, null)
                    .setRevision(1)
                    .setDeleted(NOT_DELETED)
                    .setCreateTime(now)
                    .setUpdateTime(now);
            if (assetReleaseStateMapper.insert(inserted) <= 0) {
                throw new IllegalStateException("insert asset release state failed");
            }
            log.info("共享发布状态已写入DB, assetType:{}, assetKey:{}, revision:{}",
                    state.getAssetType(), state.getAssetKey(), inserted.getRevision());
            return toState(inserted);
        }
        if (current.getRevision() != expectedRevision) {
            log.warn("共享发布状态版本冲突, assetType:{}, assetKey:{}, expectedRevision:{}, actualRevision:{}",
                    state.getAssetType(), state.getAssetKey(), expectedRevision, current.getRevision());
            throw new IllegalStateException(ERROR_REVISION_CONFLICT);
        }
        AssetReleaseStateDO updated = toDO(state, current)
                .setId(current.getId())
                .setRevision(expectedRevision + 1)
                .setDeleted(NOT_DELETED)
                .setCreateTime(current.getCreateTime())
                .setUpdateTime(now);
        int rows = assetReleaseStateMapper.update(updated, new LambdaUpdateWrapper<AssetReleaseStateDO>()
                .eq(AssetReleaseStateDO::getId, current.getId())
                .eq(AssetReleaseStateDO::getRevision, expectedRevision)
                .eq(AssetReleaseStateDO::getDeleted, NOT_DELETED));
        if (rows <= 0) {
            throw new IllegalStateException(ERROR_REVISION_CONFLICT);
        }
        log.info("共享发布状态DB更新完成, assetType:{}, assetKey:{}, revision:{}->{}",
                state.getAssetType(), state.getAssetKey(), expectedRevision, updated.getRevision());
        return toState(updated);
    }

    private AssetReleaseStateDO toDO(AssetReleaseState state, AssetReleaseStateDO previous) {
        return new AssetReleaseStateDO()
                .setAssetType(state.getAssetType())
                .setAssetKey(state.getAssetKey())
                .setStateJson(SkillFactoryJsonColumnSupport.required(
                        recordStore.split(state, previous), "stateJson"));
    }

    private AssetReleaseState toState(AssetReleaseStateDO stateDO) {
        String hydrated = recordStore.hydrate(stateDO.getAssetType(), stateDO.getAssetKey(), stateDO.getStateJson());
        AssetReleaseState state = JsonSupport.fromJSON(hydrated, AssetReleaseState.class);
        if (state == null) {
            state = new AssetReleaseState()
                    .setAssetType(stateDO.getAssetType())
                    .setAssetKey(stateDO.getAssetKey());
        }
        return state.setRevision(stateDO.getRevision());
    }

    private String storageKey(String assetType, String assetKey) {
        return assetType + KEY_SEPARATOR + assetKey;
    }

}
