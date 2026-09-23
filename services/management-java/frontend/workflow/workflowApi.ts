import { callSkillFactory, SkillFactoryMethod } from '../api';
import { jsonParse } from '../shared/safeJson';
import type {
  WorkflowCreateResult,
  WorkflowDefinitionView,
  WorkflowDraft,
  WorkflowDraftPayloadView,
  WorkflowDraftUpdateResult,
  WorkflowGraphPreviewResult,
  WorkflowListPageView,
  WorkflowSkillOption,
} from './types';
import { serializeWorkflowDraft } from './model';

const parseDraftPayload = (view: WorkflowDraftPayloadView): WorkflowDraft => {
  const parsed = jsonParse(view.draftPayloadJson, null) as unknown;
  if (parsed === null) {
    throw new Error('Workflow 草稿不是合法 JSON，请联系后端排查');
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Workflow 草稿结构无效，请联系后端排查');
  }
  return parsed as WorkflowDraft;
};

export interface WorkflowDraftDetail {
  draft: WorkflowDraft;
  draftRevision: number;
  draftDigest?: string;
}

export const workflowApi = {
  create: (payload: { displayName: string; description: string; specialistCode: string }) =>
    callSkillFactory<WorkflowCreateResult>(SkillFactoryMethod.WORKFLOW_CREATE, payload),
  detail: (workflowCode: string) =>
    callSkillFactory<WorkflowDefinitionView>(SkillFactoryMethod.WORKFLOW_DETAIL, { workflowCode }),
  list: (params: { specialistCode?: string; pageToken?: string; limit?: number }) =>
    callSkillFactory<WorkflowListPageView>(SkillFactoryMethod.WORKFLOW_LIST, params),
  updateBasicInfo: (payload: {
    workflowCode: string;
    displayName?: string;
    description?: string;
  }) =>
    callSkillFactory<WorkflowDefinitionView>(
      SkillFactoryMethod.WORKFLOW_BASIC_INFO_UPDATE,
      payload,
    ),
  draft: async (workflowCode: string): Promise<WorkflowDraftDetail> => {
    const view = await callSkillFactory<WorkflowDraftPayloadView>(
      SkillFactoryMethod.WORKFLOW_DRAFT_DETAIL,
      { workflowCode },
    );
    return {
      draft: parseDraftPayload(view),
      draftRevision: view.draftRevision,
      draftDigest: view.draftDigest,
    };
  },
  saveDraft: (workflowCode: string, draft: WorkflowDraft, expectedDraftRevision: number) =>
    callSkillFactory<WorkflowDraftUpdateResult>(SkillFactoryMethod.WORKFLOW_DRAFT_UPDATE, {
      workflowCode,
      draftPayloadJson: serializeWorkflowDraft(draft),
      expectedDraftRevision,
    }),
  skills: (workflowCode: string) =>
    callSkillFactory<WorkflowSkillOption[]>(SkillFactoryMethod.WORKFLOW_SKILL_CANDIDATES, {
      workflowCode,
    }),
  preview: (workflowCode: string, draft: WorkflowDraft) =>
    callSkillFactory<WorkflowGraphPreviewResult>(
      SkillFactoryMethod.WORKFLOW_COMPILED_PLAN_PREVIEW,
      {
        workflowCode,
        draftPayloadJson: serializeWorkflowDraft(draft),
      },
    ),
};
