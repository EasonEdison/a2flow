package dev.a2flow.management.storage.db.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import dev.a2flow.management.storage.db.entity.WorkflowDefinitionDO;

/**
 * Workflow 定义表 Mapper。
 *
 * <p>该 Mapper 只承接 {@code workflow_definition} 表的 DB 读写，所有自定义 SQL 均声明在
 * {@code storage/db/mapper/WorkflowDefinitionMapper.xml} 中，禁止在此直接写内联 SQL。
 *
 * <p>上游：WorkflowDefinitionRepository（唯一合法调用方）。
 * <p>不负责：业务校验、乐观并发逻辑（由 Repository 依据 affectedRows 判断）、
 * 运行态表（workflow_run / workflow_run_item）访问。
 */
@Mapper
public interface WorkflowDefinitionMapper extends BaseMapper<WorkflowDefinitionDO> {

    /**
     * 全字段写入 Workflow 定义，回填自增 id。
     * SQL 在 XML 中，使用 useGeneratedKeys + keyProperty="record.id" 回填。
     */
    int insertWorkflow(@Param("record") WorkflowDefinitionDO workflowDefinitionDO);

    /**
     * 按 workflowCode 查询单条未删除记录。
     */
    WorkflowDefinitionDO selectByWorkflowCode(@Param("workflowCode") String workflowCode);

    /**
     * 按可选 specialistCode 使用 (update_time,id) 倒序 keyset 分页。
     * 两个 cursor 必须同时为空（首页）或同时非空（后续页），禁止 offset。
     */
    List<WorkflowDefinitionDO> listByCondition(
            @Param("specialistCode") String specialistCode,
            @Param("cursorUpdateTime") Long cursorUpdateTime,
            @Param("cursorId") Long cursorId,
            @Param("limit") int limit);

    /**
     * 更新基础信息（displayName / description / updatedBy / updateTime）。
     * WHERE workflow_code AND deleted=0；绝不修改 workflowCode / specialistCode。
     */
    int updateBasicInfo(
            @Param("workflowCode") String workflowCode,
            @Param("displayName") String displayName,
            @Param("description") String description,
            @Param("updatedBy") String updatedBy,
            @Param("updateTime") long updateTime);

    /**
     * 原子 CAS 更新草稿。
     * SET draft_payload_json / draft_digest / draft_contract_version / updated_by / update_time /
     *     draft_revision = draft_revision + 1
     * WHERE workflow_code AND draft_revision = expectedDraftRevision AND deleted = 0。
     * 返回受影响行数（0=版本冲突，1=成功，>1=数据异常）。
     */
    int compareAndSetDraft(
            @Param("workflowCode") String workflowCode,
            @Param("draftPayloadJson") String draftPayloadJson,
            @Param("draftDigest") String draftDigest,
            @Param("draftContractVersion") int draftContractVersion,
            @Param("updatedBy") String updatedBy,
            @Param("updateTime") long updateTime,
            @Param("expectedDraftRevision") long expectedDraftRevision);
}
