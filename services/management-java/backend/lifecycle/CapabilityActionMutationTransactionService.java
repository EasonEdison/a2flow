package dev.a2flow.management.lifecycle;

import jakarta.annotation.Resource;

import org.springframework.stereotype.Service;

import org.springframework.transaction.annotation.Transactional;
import dev.a2flow.management.lifecycle.CapabilityActionClassificationRelationService.ClassificationSelection;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.storage.db.mapper.SkillFactoryMapperConstants;
import dev.a2flow.management.storage.db.repository.CapabilityActionDraftRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * 业务能力草稿变更短事务编排服务。
 *
 * <p>草稿 revision 和相同 revision 的实体关系必须在同一 sellerDataManager 事务中提交；本类不做
 * 参数解析、权限判断、发布或运行态读取。
 */
@Service
@Slf4j
public class CapabilityActionMutationTransactionService {

    @Resource
    private CapabilityActionDraftRepository capabilityActionDraftRepository;

    @Resource
    private CapabilityActionClassificationRelationService classificationRelationService;

    /** 保存草稿并用受控选择替换新 revision 分类关系。 */
    @Transactional(rollbackFor = Exception.class)
    public CapabilityActionDraft save(String operator, CapabilityActionDraft draft,
            int expectedRevision, ClassificationSelection selection) {
        CapabilityActionDraft saved = capabilityActionDraftRepository.update(draft, expectedRevision);
        classificationRelationService.copyAndReplaceForRevision(
                saved.getDraftId(), expectedRevision, saved.getRevision(), selection, operator);
        log.info("业务能力草稿与分类关系保存完成, draftId:{}, revision:{}, operator:{}",
                saved.getDraftId(), saved.getRevision(), operator);
        return classificationRelationService.project(saved);
    }

    /** 保存不改变分类的校验结果，并完整继承关系到新 revision。 */
    @Transactional(rollbackFor = Exception.class)
    public CapabilityActionDraft saveWithInheritedRelations(String operator, CapabilityActionDraft draft,
            int expectedRevision) {
        CapabilityActionDraft saved = capabilityActionDraftRepository.update(draft, expectedRevision);
        classificationRelationService.copyForRevision(
                saved.getDraftId(), expectedRevision, saved.getRevision(), operator);
        log.info("业务能力草稿校验结果与关系版本保存完成, draftId:{}, revision:{}, operator:{}",
                saved.getDraftId(), saved.getRevision(), operator);
        return classificationRelationService.project(saved);
    }
}
