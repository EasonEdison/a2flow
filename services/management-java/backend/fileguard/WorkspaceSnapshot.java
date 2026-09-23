package dev.a2flow.management.fileguard;

import java.util.Map;

import com.google.common.collect.Maps;

import lombok.Data;

/**
 * SkillFactory workspace 文件快照。
 *
 * <p>该对象只保存某个工作目录在某一时刻的文件树摘要和逐文件摘要，供 AI Coding、
 * ZIP 导入、手工编辑等能力之间做变更检测和 CAS 判断。它不保存文件正文，不承担任何写文件动作。
 */
@Data
public class WorkspaceSnapshot {

    private String rootPath;
    private String fileTreeDigest;
    private Map<String, String> fileDigestMap = Maps.newLinkedHashMap();
    private int fileCount;
    private long snapshotTime;

    public static WorkspaceSnapshot empty(String rootPath, String fileTreeDigest) {
        WorkspaceSnapshot snapshot = new WorkspaceSnapshot();
        snapshot.setRootPath(rootPath);
        snapshot.setFileTreeDigest(fileTreeDigest);
        snapshot.setFileDigestMap(Maps.newLinkedHashMap());
        snapshot.setFileCount(0);
        snapshot.setSnapshotTime(System.currentTimeMillis());
        return snapshot;
    }

    public Map<String, String> safeFileDigestMap() {
        return fileDigestMap == null ? Maps.newLinkedHashMap() : fileDigestMap;
    }
}
