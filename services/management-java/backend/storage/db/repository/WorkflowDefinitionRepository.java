package dev.a2flow.management.storage.db.repository;

import java.util.List;

import jakarta.annotation.Resource;

import org.springframework.stereotype.Repository;

import dev.a2flow.management.storage.db.entity.WorkflowDefinitionDO;
import dev.a2flow.management.storage.db.mapper.WorkflowDefinitionMapper;

import lombok.extern.slf4j.Slf4j;

/**
 * Workflow 定义表 Repository。
 *
 * <p>该 Repository 是 {@code workflow_definition} 表的唯一读写边界，负责 DO 级数据访问与
 * 乐观并发结果判断。所有 SQL 均通过 {@link WorkflowDefinitionMapper} XML 方法执行，
 * 禁止在本类使用 LambdaQueryWrapper / LambdaUpdateWrapper 拼装业务 SQL。
 *
 * <p>调用方（WorkflowDefinitionService）必须在调用前完整构造 DO 字段，包括业务默认值
 * （draftRevision / draftContractVersion / draftDigest / deleted / createTime / updateTime 等），
 * 本类不承担任何业务默认值的构造。
 *
 * <p>上游：WorkflowDefinitionService、资产授权与创建事务服务、WorkflowSpecialistSkillSelector。
 * <p>下游：WorkflowDefinitionMapper → workflow_definition 表。
 * <p>不负责：业务规则校验、专员白名单核对、图编译、发布门禁、运行态表访问、业务字段默认值构造。
 */
@Repository
@Slf4j
public class WorkflowDefinitionRepository {

    private static final int INSERT_SUCCESS_ROWS = 1;
    private static final int CAS_SUCCESS_ROWS = 1;

    @Resource
    private WorkflowDefinitionMapper workflowDefinitionMapper;

    /**
     * 写入调用方已完整构造的 WorkflowDefinitionDO，回填自增 id。
     * 调用方必须在调用前完整填充所有字段（包括 draftRevision / draftDigest / deleted / createTime 等）；
     * 本方法不构造任何业务默认值。
     * affectedRows 必须恰好为 1，否则 fail closed 抛出异常。
     */
    public WorkflowDefinitionDO insert(WorkflowDefinitionDO workflowDefinitionDO) {
        int rows = workflowDefinitionMapper.insertWorkflow(workflowDefinitionDO);
        if (rows != INSERT_SUCCESS_ROWS) {
            log.error("Workflow 定义写入 DB 失败, workflowCode:{}, affectedRows:{}",
                    workflowDefinitionDO.getWorkflowCode(), rows);
            throw new IllegalStateException("workflow definition insert failed, workflowCode="
                    + workflowDefinitionDO.getWorkflowCode() + ", affectedRows=" + rows);
        }
        log.info("Workflow 定义写入 DB 成功, workflowCode:{}, id:{}",
                workflowDefinitionDO.getWorkflowCode(), workflowDefinitionDO.getId());
        return workflowDefinitionDO;
    }

    /**
     * 按 workflowCode 查询单条未删除记录，不存在则返回 null。
     */
    public WorkflowDefinitionDO findByWorkflowCode(String workflowCode) {
        WorkflowDefinitionDO result = workflowDefinitionMapper.selectByWorkflowCode(workflowCode);
        if (result == null) {
            log.info("Workflow 定义 DB 未命中, workflowCode:{}", workflowCode);
        }
        return result;
    }

    /**
     * 使用 (updateTime,id) 倒序 keyset 查询 Workflow 定义列表。
     * specialistCode 可为空；两个 cursor 必须同时为空或同时非空。
     */
    public List<WorkflowDefinitionDO> list(String specialistCode,
            Long cursorUpdateTime, Long cursorId, int limit) {
        if ((cursorUpdateTime == null) != (cursorId == null) || limit <= 0) {
            throw new IllegalArgumentException("workflow cursor fields must be paired and limit must be positive");
        }
        return workflowDefinitionMapper.listByCondition(
                specialistCode, cursorUpdateTime, cursorId, limit);
    }

    /**
     * 更新基础信息（displayName / description / updatedBy / updateTime）。
     * 不修改 workflowCode / specialistCode；updateTime 由调用方传入。
     */
    public int updateBasicInfo(String workflowCode, String displayName, String description,
            String updatedBy, long updateTime) {
        int rows = workflowDefinitionMapper.updateBasicInfo(workflowCode, displayName, description,
                updatedBy, updateTime);
        log.info("Workflow 基础信息更新完成, workflowCode:{}, affectedRows:{}", workflowCode, rows);
        return rows;
    }

    /**
     * 原子 CAS 更新草稿。
     * 仅当 draft_revision == expectedDraftRevision 时 UPDATE 生效，成功后 draft_revision 自动 +1。
     * updateTime 由调用方传入。
     *
     * @return true=更新成功；false=版本冲突（0 affectedRows）
     * @throws IllegalStateException affectedRows > 1，表示数据异常，fail closed 不降级
     */
    public boolean compareAndSetDraft(String workflowCode, String draftPayloadJson,
            String draftDigest, int draftContractVersion, String updatedBy,
            long updateTime, long expectedDraftRevision) {
        int affectedRows = workflowDefinitionMapper.compareAndSetDraft(
                workflowCode, draftPayloadJson, draftDigest,
                draftContractVersion, updatedBy, updateTime, expectedDraftRevision);
        if (affectedRows == CAS_SUCCESS_ROWS) {
            log.info("Workflow 草稿 CAS 更新成功, workflowCode:{}, expectedRevision:{}",
                    workflowCode, expectedDraftRevision);
            return true;
        }
        if (affectedRows == 0) {
            log.info("Workflow 草稿 CAS 版本冲突, workflowCode:{}, expectedRevision:{}",
                    workflowCode, expectedDraftRevision);
            return false;
        }
        log.error("Workflow 草稿 CAS 返回异常行数, workflowCode:{}, expectedRevision:{}, affectedRows:{}",
                workflowCode, expectedDraftRevision, affectedRows);
        throw new IllegalStateException("compareAndSetDraft returned unexpected affectedRows="
                + affectedRows + " for workflowCode=" + workflowCode);
    }
}
