package dev.a2flow.management.storage.db.repository;

import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Consumer;

import jakarta.annotation.Resource;

import org.springframework.stereotype.Repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.storage.db.entity.AssetReleaseStateDO;
import dev.a2flow.management.storage.db.entity.ReleaseRecordHeader;
import dev.a2flow.management.storage.db.mapper.AssetReleaseStateMapper;
import dev.a2flow.management.storage.db.mapper.ReleaseRecordHeaderMapper;
import dev.a2flow.management.support.JsonSupport;

/**
 * 当前环境快照专用读模型：历史只读索引，正文只加载环境命中的记录和版本所需的 Build。
 *
 * <p>返回的是裁剪后的临时聚合，绝不能用于发布写入或历史详情。完整聚合仍由
 * AssetReleaseStateRepository 管理。选中记录继续复用原存储编解码器进行摘要、归属及快照引用校验。
 */
@Repository
public class PublishedReleaseStateRepository {
    private static final int PAGE_SIZE = 100;
    private static final int HEADER_BATCH_SIZE = 200;
    private static final String ERROR_INVALID = "release record storage is invalid";

    @Resource
    private AssetReleaseStateMapper stateMapper;
    @Resource
    private ReleaseRecordHeaderMapper headerMapper;
    @Resource
    private AssetReleaseRecordStore recordStore;

    public AssetReleaseState find(ReleaseAssetType assetType, String assetKey,
            Set<ReleaseEnvironment> environments) {
        AssetReleaseStateDO row = stateMapper.selectOne(baseQuery(assetType)
                .eq(AssetReleaseStateDO::getAssetKey, assetKey).last("LIMIT 1"));
        if (row == null) {
            return new AssetReleaseState().setAssetType(assetType.name()).setAssetKey(assetKey).setRevision(0);
        }
        return readSelected(row, environments);
    }

    public void scan(ReleaseAssetType assetType, ReleaseEnvironment environment,
            Consumer<AssetReleaseState> consumer) {
        String cursor = null;
        while (true) {
            List<AssetReleaseStateDO> rows = stateMapper.selectList(baseQuery(assetType)
                    .gt(cursor != null, AssetReleaseStateDO::getAssetKey, cursor)
                    .orderByAsc(AssetReleaseStateDO::getAssetKey).last("LIMIT " + PAGE_SIZE));
            for (AssetReleaseStateDO row : rows) {
                consumer.accept(readSelected(row, EnumSet.of(environment)));
            }
            if (rows.size() < PAGE_SIZE) {
                return;
            }
            cursor = rows.get(rows.size() - 1).getAssetKey();
        }
    }

    private LambdaQueryWrapper<AssetReleaseStateDO> baseQuery(ReleaseAssetType assetType) {
        return new LambdaQueryWrapper<AssetReleaseStateDO>()
                .eq(AssetReleaseStateDO::getAssetType, assetType.name())
                .eq(AssetReleaseStateDO::getDeleted, 0);
    }

    private AssetReleaseState readSelected(AssetReleaseStateDO row, Set<ReleaseEnvironment> environments) {
        JsonNode root = JsonSupport.fromJSON(row.getStateJson(), JsonNode.class);
        require(root != null && root.isObject());
        if (!root.has("recordStorageVersion")) {
            // 老内联聚合无独立索引，保持原读取语义，不隐式迁移或伪造发布状态。
            return JsonSupport.fromJSON(row.getStateJson(), AssetReleaseState.class).setRevision(row.getRevision());
        }
        require(root.path("recordStorageVersion").isIntegralNumber()
                && root.path("recordStorageVersion").intValue() == 1);
        require(row.getAssetType().equals(text(root, "assetType"))
                && row.getAssetKey().equals(text(root, "assetKey")));
        Map<String, ReleaseRecordHeader> headers = loadHeaders(root);
        List<StoredEntry> builds = entries(row, root, "builds", headers);
        List<StoredEntry> versions = entries(row, root, "versions", headers);
        Map<String, StoredEntry> buildsById = new HashMap<>();
        for (StoredEntry build : builds) {
            String buildId = build.header().buildId();
            require(buildId != null && !buildId.isEmpty() && buildsById.put(buildId, build) == null);
        }
        Set<StoredEntry> selectedBuilds = new HashSet<>();
        Set<StoredEntry> selectedVersions = new HashSet<>();
        for (ReleaseEnvironment environment : environments) {
            JsonNode pointer = root.path("environments").path(environment.name());
            Integer version = integer(pointer, "version");
            if (version == null) {
                continue;
            }
            if ("BUILD".equals(text(pointer, "sourceType"))) {
                builds.stream().filter(entry -> Objects.equals(entry.header().buildId(), text(pointer, "sourceId")))
                        .filter(entry -> Objects.equals(entry.header().targetVersion(), version))
                        .filter(entry -> entry.header().snapshotPresent()).findFirst().ifPresent(selectedBuilds::add);
            } else {
                versions.stream().filter(entry -> Objects.equals(entry.header().version(), version))
                        .filter(entry -> entry.header().snapshotPresent() || entry.header().snapshotBuildId() != null)
                        .findFirst().ifPresent(entry -> {
                            selectedVersions.add(entry);
                            String buildId = entry.header().snapshotBuildId();
                            if (buildId != null) {
                                StoredEntry sourceBuild = buildsById.get(buildId);
                                require(sourceBuild != null);
                                selectedBuilds.add(sourceBuild);
                            }
                        });
            }
        }
        ObjectNode selected = JsonSupport.mapper().createObjectNode();
        selected.put("recordStorageVersion", 1);
        selected.put("assetType", row.getAssetType());
        selected.put("assetKey", row.getAssetKey());
        selected.set("environments", root.path("environments"));
        copySelected(selected, root, "builds", builds, selectedBuilds);
        copySelected(selected, root, "versions", versions, selectedVersions);
        selected.putArray("deployments");
        String hydrated = recordStore.hydrate(row.getAssetType(), row.getAssetKey(), selected.toString());
        return JsonSupport.fromJSON(hydrated, AssetReleaseState.class).setRevision(row.getRevision());
    }

    private Map<String, ReleaseRecordHeader> loadHeaders(JsonNode root) {
        List<String> refs = new ArrayList<>();
        for (String collection : List.of("builds", "versions")) {
            for (JsonNode item : array(root, collection)) {
                require(item.isObject());
                if (item.has("recordRef")) {
                    String ref = text(item, "recordRef");
                    require(item.size() == 1 && ref != null && !ref.isEmpty());
                    refs.add(ref);
                }
            }
        }
        Map<String, ReleaseRecordHeader> headers = new HashMap<>();
        for (int start = 0; start < refs.size(); start += HEADER_BATCH_SIZE) {
            List<String> batch = refs.subList(start, Math.min(start + HEADER_BATCH_SIZE, refs.size()));
            for (ReleaseRecordHeader header : headerMapper.selectHeaders(batch)) {
                headers.put(header.recordRef(), header);
            }
        }
        return headers;
    }

    private List<StoredEntry> entries(AssetReleaseStateDO row, JsonNode root, String collection,
            Map<String, ReleaseRecordHeader> headers) {
        List<StoredEntry> result = new ArrayList<>();
        for (JsonNode storage : array(root, collection)) {
            ReleaseRecordHeader header;
            if (storage.has("recordRef")) {
                header = headers.get(text(storage, "recordRef"));
                require(header != null && header.checksumValid() && row.getAssetType().equals(header.assetType())
                        && row.getAssetKey().equals(header.assetKey()) && collection.equals(header.collection())
                        && header.recordId() != null && !header.recordId().isEmpty()
                        && header.recordId().equals(header.payloadRecordId()));
            } else {
                header = new ReleaseRecordHeader(null, row.getAssetType(), row.getAssetKey(), collection,
                        null, null, text(storage, "buildId"), integer(storage, "targetVersion"),
                        integer(storage, "version"), storage.hasNonNull("snapshot"), text(storage, "snapshotBuildId"), true);
            }
            result.add(new StoredEntry(storage, header));
        }
        return result;
    }

    private void copySelected(ObjectNode target, JsonNode root, String collection,
            List<StoredEntry> original, Set<StoredEntry> selected) {
        if (!root.hasNonNull(collection)) {
            target.putNull(collection);
            return;
        }
        var array = target.putArray(collection);
        original.stream().filter(selected::contains).forEach(entry -> array.add(entry.storage()));
    }

    private Iterable<JsonNode> array(JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || value.isNull()) {
            return List.of();
        }
        require(value.isArray());
        return value;
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        require(value == null || value.isNull() || value.isTextual());
        return value == null || value.isNull() ? null : value.textValue();
    }

    private static Integer integer(JsonNode node, String field) {
        JsonNode value = node.get(field);
        require(value == null || value.isNull() || value.isIntegralNumber() && value.canConvertToInt());
        return value == null || value.isNull() ? null : value.intValue();
    }

    private static void require(boolean valid) {
        if (!valid) {
            throw new IllegalStateException(ERROR_INVALID);
        }
    }

    private record StoredEntry(JsonNode storage, ReleaseRecordHeader header) { }
}
