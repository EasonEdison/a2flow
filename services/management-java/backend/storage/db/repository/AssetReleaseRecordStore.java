package dev.a2flow.management.storage.db.repository;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseDigestUtils;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.storage.db.entity.AssetReleaseStateDO;
import dev.a2flow.management.storage.db.mapper.AssetReleaseStateMapper;

import lombok.extern.slf4j.Slf4j;

/**
 * 同表不可变发布记录的持久化编解码边界。
 *
 * <p>原资产行保存轻量引用，新增或变更的 Build、Version、Deployment 以内容摘要为键独立落行。
 * 旧内联历史不批量迁移；只有本次改变的条目拆行。子行不可变，根行 CAS 前的写入由上游短事务承接，
 * 因此并发读到任一根行都能还原同一份快照。缺失、篡改、跨资产引用一律失败，不回读草稿。
 */
@Component
@Slf4j
public class AssetReleaseRecordStore {
    private static final String RECORD_TYPE = "RELEASE_RECORD";
    private static final String FORMAT = "recordStorageVersion";
    private static final int FORMAT_VERSION = 1;
    private static final String REF = "recordRef";
    private static final String PARENT_TYPE = "assetType";
    private static final String PARENT_KEY = "assetKey";
    private static final String COLLECTION = "collection";
    private static final String RECORD_ID = "recordId";
    private static final String PAYLOAD = "payload";
    private static final String RECORD_JSON = "recordJson";
    private static final String BUILDS = "builds";
    private static final String VERSIONS = "versions";
    private static final String DEPLOYMENTS = "deployments";
    private static final String BUILD_ID = "buildId";
    private static final String VERSION_ID = "versionId";
    private static final String DEPLOYMENT_ID = "deploymentId";
    private static final String SNAPSHOT = "snapshot";
    private static final String SNAPSHOT_BUILD_ID = "snapshotBuildId";
    private static final String SOURCE_DIGEST = "sourceDigest";
    private static final String SOURCE_BUILD_ID = "sourceBuildId";
    private static final String INPUT_DIGEST = "inputDigest";
    private static final String DIGEST = "digest";
    private static final String PAYLOAD_JSON = "payloadJson";
    private static final String DIGEST_PREFIX = "sha256:";
    private static final String ERROR_INVALID = "release record storage is invalid";
    private static final int NOT_DELETED = 0;
    private static final int QUERY_BATCH_SIZE = 200;
    private static final List<String> COLLECTIONS = List.of(BUILDS, VERSIONS, DEPLOYMENTS);
    private static final Map<String, String> ID_FIELDS = Map.of(
            BUILDS, BUILD_ID, VERSIONS, VERSION_ID, DEPLOYMENTS, DEPLOYMENT_ID);

    @Resource
    private AssetReleaseStateMapper mapper;

    /** 将持久化引用还原为领域聚合；无格式标记的历史聚合保持原读语义。 */
    public String hydrate(String assetType, String assetKey, String stateJson) {
        Map<String, Object> root = object(stateJson);
        if (!root.containsKey(FORMAT)) {
            return stateJson;
        }
        require(Objects.equals(root.remove(FORMAT), FORMAT_VERSION));
        Map<String, AssetReleaseStateDO> records = loadRecords(root);
        for (String collection : COLLECTIONS) {
            List<Map<String, Object>> hydrated = new ArrayList<>();
            for (Map<String, Object> item : entries(root, collection)) {
                if (!item.containsKey(REF)) {
                    hydrated.add(item);
                    continue;
                }
                require(item.size() == 1);
                String key = text(item.get(REF));
                AssetReleaseStateDO record = records.get(key);
                require(record != null);
                String recordJson = recordJson(record);
                require(key.equals(ReleaseDigestUtils.sha256(recordJson)));
                Map<String, Object> envelope = object(recordJson);
                require(assetType.equals(envelope.get(PARENT_TYPE))
                        && assetKey.equals(envelope.get(PARENT_KEY))
                        && collection.equals(envelope.get(COLLECTION)));
                Map<String, Object> payload = map(envelope.get(PAYLOAD));
                require(text(envelope.get(RECORD_ID)).equals(payload.get(ID_FIELDS.get(collection))));
                hydrated.add(payload);
            }
            if (root.get(collection) != null) {
                root.put(collection, hydrated);
            }
        }
        restoreVersionSnapshots(root);
        return JsonSupport.toJSON(root);
    }

    /** 在根行写入事务内保存改变的记录；相同历史条目保留原内联内容或原引用。 */
    public String split(AssetReleaseState state, AssetReleaseStateDO previous) {
        Map<String, Object> desired = object(JsonSupport.toJSON(state));
        Map<String, Map<String, Object>> builds = index(entries(desired, BUILDS), BUILDS);
        Map<String, Object> persisted = previous == null ? new LinkedHashMap<>() : object(previous.getStateJson());
        Map<String, Object> old = previous == null ? new LinkedHashMap<>()
                : object(hydrate(state.getAssetType(), state.getAssetKey(), previous.getStateJson()));
        for (String collection : COLLECTIONS) {
            Map<String, Map<String, Object>> previousValues = index(entries(old, collection), collection);
            Map<String, Map<String, Object>> previousStorage = new HashMap<>();
            List<Map<String, Object>> oldValues = entries(old, collection);
            List<Map<String, Object>> oldStorage = entries(persisted, collection);
            require(oldValues.size() == oldStorage.size());
            for (int i = 0; i < oldValues.size(); i++) {
                previousStorage.put(text(oldValues.get(i).get(ID_FIELDS.get(collection))), oldStorage.get(i));
            }
            List<Map<String, Object>> next = new ArrayList<>();
            for (Map<String, Object> value : entries(desired, collection)) {
                String id = text(value.get(ID_FIELDS.get(collection)));
                if (value.equals(previousValues.get(id))) {
                    next.add(previousStorage.get(id));
                } else {
                    Map<String, Object> payload = compactVersion(collection, value, builds);
                    next.add(Map.of(REF, saveRecord(state, collection, id, payload)));
                }
            }
            desired.put(collection, next);
        }
        desired.put(FORMAT, FORMAT_VERSION);
        return JsonSupport.toJSON(desired);
    }

    /** 相同快照复用 Build 引用；A2UI 线上派生快照独立保存，仍校验来源、资产身份和内容摘要。 */
    private Map<String, Object> compactVersion(String collection, Map<String, Object> value,
            Map<String, Map<String, Object>> builds) {
        Map<String, Object> payload = new LinkedHashMap<>(value);
        if (VERSIONS.equals(collection) && value.get(SNAPSHOT) != null) {
            Map<String, Object> build = builds.get(text(value.get(SOURCE_BUILD_ID)));
            require(build != null && Objects.equals(value.get(INPUT_DIGEST), inputDigest(build)));
            if (!Objects.equals(value.get(SNAPSHOT), build.get(SNAPSHOT))) {
                Map<String, Object> snapshot = map(value.get(SNAPSHOT));
                Map<String, Object> buildSnapshot = map(build.get(SNAPSHOT));
                require(ReleaseAssetType.A2UI_APPLICATION.name().equals(snapshot.get(PARENT_TYPE))
                        && Objects.equals(snapshot.get(PARENT_TYPE), buildSnapshot.get(PARENT_TYPE))
                        && Objects.equals(snapshot.get(PARENT_KEY), buildSnapshot.get(PARENT_KEY))
                        && Objects.equals(value.get(SOURCE_DIGEST), snapshot.get(DIGEST))
                        && Objects.equals(snapshot.get(DIGEST),
                                DIGEST_PREFIX + ReleaseDigestUtils.sha256(text(snapshot.get(PAYLOAD_JSON)))));
                return payload;
            }
            require(Objects.equals(value.get(SOURCE_DIGEST), build.get(SOURCE_DIGEST)));
            payload.remove(SNAPSHOT);
            payload.put(SNAPSHOT_BUILD_ID, build.get(BUILD_ID));
        }
        return payload;
    }

    /** 子行以完整内容摘要寻址；相同内容复用，禁止更新已存在的不可变记录。 */
    private String saveRecord(AssetReleaseState state, String collection, String id, Map<String, Object> payload) {
        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put(PARENT_TYPE, state.getAssetType());
        envelope.put(PARENT_KEY, state.getAssetKey());
        envelope.put(COLLECTION, collection);
        envelope.put(RECORD_ID, id);
        envelope.put(PAYLOAD, payload);
        String json = JsonSupport.toJSON(envelope);
        String key = ReleaseDigestUtils.sha256(json);
        AssetReleaseStateDO existing = mapper.selectOne(new LambdaQueryWrapper<AssetReleaseStateDO>()
                .eq(AssetReleaseStateDO::getAssetType, RECORD_TYPE)
                .eq(AssetReleaseStateDO::getAssetKey, key));
        if (existing != null) {
            require(Objects.equals(existing.getDeleted(), NOT_DELETED) && json.equals(recordJson(existing)));
            return key;
        }
        long now = System.currentTimeMillis();
        int rows = mapper.insert(new AssetReleaseStateDO().setAssetType(RECORD_TYPE).setAssetKey(key)
                .setStateJson(JsonSupport.toJSON(Map.of(RECORD_JSON, json)))
                .setRevision(FORMAT_VERSION).setDeleted(NOT_DELETED)
                .setCreateTime(now).setUpdateTime(now));
        require(rows == 1);
        log.info("共享发布独立记录已保存, assetType:{}, assetKey:{}, collection:{}, recordId:{}",
                state.getAssetType(), state.getAssetKey(), collection, id);
        return key;
    }

    private Map<String, AssetReleaseStateDO> loadRecords(Map<String, Object> root) {
        List<String> keys = new ArrayList<>();
        for (String collection : COLLECTIONS) {
            for (Map<String, Object> item : entries(root, collection)) {
                if (item.containsKey(REF)) {
                    keys.add(text(item.get(REF)));
                }
            }
        }
        Map<String, AssetReleaseStateDO> result = new HashMap<>();
        for (int start = 0; start < keys.size(); start += QUERY_BATCH_SIZE) {
            List<String> batch = keys.subList(start, Math.min(start + QUERY_BATCH_SIZE, keys.size()));
            List<AssetReleaseStateDO> rows = mapper.selectList(new LambdaQueryWrapper<AssetReleaseStateDO>()
                    .eq(AssetReleaseStateDO::getAssetType, RECORD_TYPE)
                    .eq(AssetReleaseStateDO::getDeleted, NOT_DELETED)
                    .in(AssetReleaseStateDO::getAssetKey, batch));
            for (AssetReleaseStateDO row : rows) {
                result.put(row.getAssetKey(), row);
            }
        }
        return result;
    }

    private void restoreVersionSnapshots(Map<String, Object> root) {
        Map<String, Map<String, Object>> builds = index(entries(root, BUILDS), BUILDS);
        for (Map<String, Object> version : entries(root, VERSIONS)) {
            if (!version.containsKey(SNAPSHOT_BUILD_ID)) {
                continue;
            }
            require(!version.containsKey(SNAPSHOT));
            String buildId = text(version.remove(SNAPSHOT_BUILD_ID));
            require(buildId.equals(version.get(SOURCE_BUILD_ID)));
            Map<String, Object> build = builds.get(buildId);
            require(build != null && build.get(SNAPSHOT) != null
                    && Objects.equals(build.get(SOURCE_DIGEST), version.get(SOURCE_DIGEST))
                    && Objects.equals(inputDigest(build), version.get(INPUT_DIGEST)));
            version.put(SNAPSHOT, build.get(SNAPSHOT));
        }
    }

    private Object inputDigest(Map<String, Object> build) {
        Object digest = build.get(INPUT_DIGEST);
        require(digest == null || digest instanceof String);
        return StringUtils.defaultIfBlank((String) digest, text(build.get(SOURCE_DIGEST)));
    }

    /** JSON 列会规范化外层文本；摘要只计算内层字符串保存的原始字节。 */
    private String recordJson(AssetReleaseStateDO record) {
        Map<String, Object> wrapper = object(record.getStateJson());
        require(wrapper.size() == 1);
        return text(wrapper.get(RECORD_JSON));
    }

    private Map<String, Map<String, Object>> index(List<Map<String, Object>> values, String collection) {
        Map<String, Map<String, Object>> result = new HashMap<>();
        for (Map<String, Object> value : values) {
            require(result.put(text(value.get(ID_FIELDS.get(collection))), value) == null);
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> entries(Map<String, Object> root, String key) {
        Object value = root.get(key);
        if (value == null) {
            return List.of();
        }
        require(value instanceof List);
        for (Object entry : (List<?>) value) {
            map(entry);
        }
        return (List<Map<String, Object>>) value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value) {
        require(value instanceof Map);
        return (Map<String, Object>) value;
    }

    private Map<String, Object> object(String json) {
        return map(JsonSupport.fromJSON(json, Map.class));
    }

    private String text(Object value) {
        require(value instanceof String && !((String) value).isEmpty());
        return (String) value;
    }

    private void require(boolean valid) {
        if (!valid) {
            throw new IllegalStateException(ERROR_INVALID);
        }
    }
}
