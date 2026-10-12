package dev.a2flow.management.storage.db.entity;

/** 发布记录的只读索引，不包含 snapshot、payloadJson 或部署详情。 */
public record ReleaseRecordHeader(
        String recordRef,
        String assetType,
        String assetKey,
        String collection,
        String recordId,
        String payloadRecordId,
        String buildId,
        Integer targetVersion,
        Integer version,
        boolean snapshotPresent,
        String snapshotBuildId,
        boolean checksumValid) {
}
