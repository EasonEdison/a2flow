import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Input, Space, Spin, Tag, Tabs, Typography, message } from 'antd';
import { ArrowLeftOutlined, ReloadOutlined, SaveOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { skillFactoryApi } from '../api';
import type { SkillFactorySpecialistOption } from '../api';
import AssetReleaseTab from '../shared/AssetReleaseTab';
import { useAssetAccess } from '../shared/AssetAccessContext';
import AssetOwnerManagement from '../shared/AssetOwnerManagement';
import {
  normalizeSkillFactorySpecialists,
  specialistOptionId,
  specialistOptionName,
} from '../shared/specialistOptions';
import WorkflowCanvas from './WorkflowCanvas';
import WorkflowInspector from './WorkflowInspector';
import { normalizeWorkflowDraft } from './model';
import { workflowApi } from './workflowApi';
import { validateWorkflowDraft } from './workflowValidation';
import { graphErrorsToIssues } from './workflowViewModel';
import type {
  WorkflowDefinitionView,
  WorkflowDraft,
  WorkflowSkillOption,
  WorkflowValidationIssue,
} from './types';
import './workflowOrchestration.less';
import './workflowAuthoringExtensions.less';

const { Text, Title } = Typography;

type WorkflowDetailSection = 'configuration' | 'publication';

const errorMessage = (cause: unknown, fallback: string): string =>
  cause instanceof Error ? cause.message : fallback;

const WorkflowOrchestrationPage: React.FC = () => {
  const navigate = useNavigate();
  const { workflowCode: pathWorkflowCode } = useParams<{ workflowCode: string }>();
  const [searchParams] = useSearchParams();
  const workflowCode = pathWorkflowCode || searchParams.get('workflowCode') || undefined;
  const workflowListPath = useMemo(() => {
    const nextSearchParams = new URLSearchParams(searchParams);
    nextSearchParams.delete('workflowCode');
    const search = nextSearchParams.toString();
    return `/management/workflows${search ? `?${search}` : ''}`;
  }, [searchParams]);
  const [definition, setDefinition] = useState<WorkflowDefinitionView>();
  const [draft, setDraft] = useState<WorkflowDraft>();
  const [draftRevision, setDraftRevision] = useState(0);
  const [skills, setSkills] = useState<WorkflowSkillOption[]>([]);
  const [specialists, setSpecialists] = useState<SkillFactorySpecialistOption[]>([]);
  const [specialistsLoaded, setSpecialistsLoaded] = useState(false);
  const [selectedNodeCode, setSelectedNodeCode] = useState<string>();
  const [issues, setIssues] = useState<WorkflowValidationIssue[]>([]);
  const [detailLoading, setDetailLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [metadataDirty, setMetadataDirty] = useState(false);
  const [draftDirty, setDraftDirty] = useState(false);
  const [errorText, setErrorText] = useState('');
  const [activeSection, setActiveSection] = useState<WorkflowDetailSection>('configuration');
  const access = useAssetAccess('ORCHESTRATION_CONFIG', workflowCode);
  const readonly = Boolean(workflowCode) && (access.loading || !access.permissions.canEdit);

  const loadDetail = useCallback(async (code: string) => {
    setDetailLoading(true);
    setErrorText('');
    try {
      const [nextDefinition, draftDetail, candidates] = await Promise.all([
        workflowApi.detail(code),
        workflowApi.draft(code),
        workflowApi.skills(code),
      ]);
      if (nextDefinition.workflowCode !== code || draftDetail.draft?.workflowCode !== code) {
        throw new Error('Workflow 详情与路由身份不一致');
      }
      const nextDraft = normalizeWorkflowDraft(draftDetail.draft);
      setDefinition(nextDefinition);
      setDraft(nextDraft);
      setDraftRevision(draftDetail.draftRevision);
      setSkills(candidates);
      setSelectedNodeCode(nextDraft.nodes?.[0]?.nodeCode);
      setIssues([]);
      setDraftDirty(false);
      setMetadataDirty(false);
    } catch (cause) {
      setDefinition(undefined);
      setDraft(undefined);
      setSkills([]);
      setErrorText(errorMessage(cause, 'Workflow 详情加载失败'));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadSpecialists = useCallback(async () => {
    setSpecialistsLoaded(false);
    try {
      const config = await skillFactoryApi.config();
      setSpecialists(normalizeSkillFactorySpecialists(config.specialists));
    } catch {
      setSpecialists([]);
    } finally {
      setSpecialistsLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (workflowCode) {
      void loadDetail(workflowCode);
    } else {
      navigate(workflowListPath, { replace: true });
    }
  }, [loadDetail, navigate, workflowCode, workflowListPath]);

  useEffect(() => {
    void loadSpecialists();
  }, [loadSpecialists]);

  const specialistDisplay = useMemo(() => {
    const specialistCode = definition?.specialistCode?.trim() || '';
    const specialist = specialists.find((item) => specialistOptionId(item) === specialistCode);
    const specialistName = specialistOptionName(specialist);
    return {
      value: specialistName || specialistCode || '-',
      unresolved: specialistsLoaded && !specialistName,
    };
  }, [definition?.specialistCode, specialists, specialistsLoaded]);

  const handleDraftChange = (nextDraft: WorkflowDraft) => {
    setDraft(nextDraft);
    setDraftDirty(true);
    setIssues(validateWorkflowDraft(nextDraft));
  };

  useEffect(() => {
    if (
      draft &&
      selectedNodeCode &&
      !draft.nodes.some((node) => node.nodeCode === selectedNodeCode)
    ) {
      setSelectedNodeCode(draft.nodes?.[0]?.nodeCode);
    }
  }, [draft, selectedNodeCode]);

  const handleSave = useCallback(async () => {
    if (!draft || !workflowCode || readonly) return;
    const localIssues = validateWorkflowDraft(draft);
    setIssues(localIssues);
    if (localIssues.length) {
      message.warning(`请先修复 ${localIssues.length} 项基础配置问题`);
      return;
    }
    setSaving(true);
    try {
      const result = await workflowApi.saveDraft(workflowCode, draft, draftRevision);
      setDraftRevision(result.draftRevision);
      setDraftDirty(false);
      message.success('Workflow 草稿已保存');
    } catch (cause) {
      const text = errorMessage(cause, 'Workflow 保存失败');
      message.error(text.includes('DRAFT_CONFLICT') ? '已有更新，请刷新后重试' : text);
    } finally {
      setSaving(false);
    }
  }, [draft, draftRevision, readonly, workflowCode]);

  useEffect(() => {
    const saveByKeyboard = (event: KeyboardEvent) => {
      if (
        !workflowCode ||
        readonly ||
        (!event.metaKey && !event.ctrlKey) ||
        event.altKey ||
        event.key?.toLowerCase?.() !== 's'
      ) {
        return;
      }
      event.preventDefault();
      if (!draftDirty || saving) return;
      void handleSave();
    };
    window.addEventListener('keydown', saveByKeyboard);
    return () => window.removeEventListener('keydown', saveByKeyboard);
  }, [draftDirty, handleSave, readonly, saving, workflowCode]);

  const handleSaveMetadata = async () => {
    if (!definition || readonly) return;
    setSaving(true);
    try {
      const updated = await workflowApi.updateBasicInfo({
        workflowCode: definition.workflowCode,
        displayName: definition.displayName,
        description: definition.description,
      });
      setDefinition(updated);
      setMetadataDirty(false);
      message.success('基础信息已保存');
    } catch (cause) {
      message.error(errorMessage(cause, '基础信息保存失败'));
    } finally {
      setSaving(false);
    }
  };

  const handlePreview = async () => {
    if (!draft || !workflowCode) return;
    setPreviewing(true);
    const localIssues = validateWorkflowDraft(draft);
    try {
      const result = await workflowApi.preview(workflowCode, draft);
      const remoteIssues = graphErrorsToIssues(result.errors || []);
      setIssues([...localIssues, ...remoteIssues]);
      if (remoteIssues.length) {
        message.warning(`后端编译返回 ${remoteIssues.length} 项错误`);
      } else if (result.compiledPlan) {
        message.success(`编译计划校验通过：${result.compiledPlan?.compiledPlanDigest}`);
      } else {
        message.error('后端未返回错误，但也没有可用 compiledPlan');
      }
    } catch (cause) {
      setIssues(localIssues);
      message.error(errorMessage(cause, '编译计划预览失败'));
    } finally {
      setPreviewing(false);
    }
  };

  const refresh = async () => {
    if (!workflowCode) return;
    await Promise.all([loadDetail(workflowCode), loadSpecialists(), access.refresh()]);
  };

  return (
    <div className="page-container workflow-orchestration-page">
      <header className="workflow-page-header">
        <div className="workflow-page-title-block">
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(workflowListPath)}>
            返回 Workflow 列表
          </Button>
          <div>
            <div className="workflow-page-title-row">
              <Title level={3}>Workflow 编排</Title>
              <Tag color="purple">真实控制面契约</Tag>
            </div>
            <Text type="secondary">五类节点 · 三类 Edge · publish-center-common-v2</Text>
          </div>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void refresh()}>
            刷新
          </Button>
          {workflowCode && !readonly && activeSection === 'configuration' ? (
            <>
              <Button
                icon={<SaveOutlined />}
                loading={saving}
                disabled={!draftDirty}
                title="保存草稿（Ctrl/Cmd+S）"
                onClick={() => void handleSave()}
              >
                保存草稿
              </Button>
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={previewing}
                onClick={() => void handlePreview()}
              >
                预览编译计划
              </Button>
            </>
          ) : null}
        </Space>
      </header>

      {errorText ? <Alert type="error" showIcon message={errorText} /> : null}
      {workflowCode && access.error ? (
        <Alert
          type="warning"
          showIcon
          message="权限加载失败，编辑已按 fail-closed 禁用"
          description={access.error}
        />
      ) : null}
      {workflowCode && readonly && !access.loading ? (
        <Alert type="info" showIcon message={access.readonlyReason || '当前用户为只读角色'} />
      ) : null}

      <Tabs
        className="workflow-section-tabs"
        activeKey={activeSection}
        onChange={(key) => setActiveSection(key as WorkflowDetailSection)}
      >
        <Tabs.TabPane tab="配置" key="configuration">
          {definition ? (
            <section className="workflow-metadata-editor">
              <div className="workflow-metadata-title">
                <div>
                  <Title level={4}>{definition.displayName || definition.workflowCode}</Title>
                  <Text type="secondary">{definition.workflowCode}</Text>
                </div>
                <Space>
                  <Tag>{definition.status}</Tag>
                  <Text>revision {draftRevision}</Text>
                </Space>
              </div>
              <div className="workflow-metadata-fields">
                <label>
                  <span>Workflow 名称</span>
                  <Input
                    disabled={readonly}
                    value={definition.displayName}
                    onChange={(event) => {
                      setDefinition({
                        ...definition,
                        displayName: event.target.value,
                      });
                      setMetadataDirty(true);
                    }}
                  />
                </label>
                <label>
                  <span>描述</span>
                  <Input
                    disabled={readonly}
                    value={definition.description}
                    onChange={(event) => {
                      setDefinition({
                        ...definition,
                        description: event.target.value,
                      });
                      setMetadataDirty(true);
                    }}
                  />
                </label>
                <label>
                  <span>所属专员</span>
                  <Space size={8} wrap>
                    <Text>{specialistDisplay.value}</Text>
                    <Tag>创建后不可修改</Tag>
                    {specialistDisplay.unresolved ? <Tag color="orange">配置未解析</Tag> : null}
                  </Space>
                </label>
                {workflowCode ? (
                  <label>
                    <span>负责人</span>
                    <AssetOwnerManagement
                      assetType="ORCHESTRATION_CONFIG"
                      assetKey={workflowCode}
                      access={access.access}
                      showLabel={false}
                      onAccessRefresh={access.refresh}
                    />
                  </label>
                ) : null}
                {!readonly ? (
                  <Button
                    loading={saving}
                    disabled={!metadataDirty}
                    onClick={() => void handleSaveMetadata()}
                  >
                    保存基础信息
                  </Button>
                ) : null}
              </div>
            </section>
          ) : null}

          <Spin spinning={detailLoading}>
            <section className="workflow-workbench-grid detail-only">
              <WorkflowCanvas
                draft={draft}
                skills={skills}
                selectedNodeCode={selectedNodeCode}
                issues={issues}
                readonly={readonly}
                onSelectNode={setSelectedNodeCode}
                onChange={handleDraftChange}
              />
              <WorkflowInspector
                draft={draft}
                selectedNodeCode={selectedNodeCode}
                specialistCode={definition?.specialistCode}
                skills={skills}
                issues={issues}
                readonly={readonly}
                onChange={handleDraftChange}
              />
            </section>
          </Spin>
        </Tabs.TabPane>
        <Tabs.TabPane tab="发布" key="publication">
          {activeSection === 'publication' && workflowCode ? (
            <section className="workflow-release-workbench">
              <AssetReleaseTab
                assetType="ORCHESTRATION_CONFIG"
                assetKey={workflowCode}
                title="Workflow 发布中心"
                showCreateChange={access.permissions?.canEdit}
                onHistoricalDraftRestore={() => loadDetail(workflowCode)}
              />
            </section>
          ) : null}
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
};

export default WorkflowOrchestrationPage;
