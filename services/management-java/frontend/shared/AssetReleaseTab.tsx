import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { normalizeUserIdWhitelist } from './userIdWhitelist';
import { Alert, Button, Card, Descriptions, Empty, Input, Modal, Select, Space, Spin, Tag, Typography, message, } from 'antd';
import { CloudUploadOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { assetReleaseApi } from '../api';
import type { AssetReleaseOperationResult, AssetReleaseOverview, ReleaseDiffDocument, ReleaseDiffEntry, ReleaseDiffViewMode, ReleaseAssetType, ReleaseEnvironment, ReleaseEnvironmentState, } from '../types';
import ReleaseDiffViewer from './releaseDiff/ReleaseDiffViewer';
import { executeReleaseOperation, isPendingReleaseOperationStatus, } from './releaseOperationFeedback';
import { AssetAccessProvider, useAssetAccessContext } from './AssetAccessContext';
import AssetOwnerManagement from './AssetOwnerManagement';
const { Text } = Typography;
const action = {
    CREATE_CHANGE: 'CREATE_CHANGE',
    DEPLOY_PREPROD: 'DEPLOY_PREPROD',
    DEPLOY_ONLINE: 'DEPLOY_ONLINE',
    FORCE_DEPLOY_ONLINE: 'FORCE_DEPLOY_ONLINE',
    REDEPLOY_HISTORY: 'REDEPLOY_HISTORY',
    START_GRAY_PREPROD: 'START_GRAY_PREPROD',
    START_GRAY_ONLINE: 'START_GRAY_ONLINE',
    ADJUST_GRAY_PREPROD: 'ADJUST_GRAY_PREPROD',
    ADJUST_GRAY_ONLINE: 'ADJUST_GRAY_ONLINE',
    STOP_GRAY_PREPROD: 'STOP_GRAY_PREPROD',
    STOP_GRAY_ONLINE: 'STOP_GRAY_ONLINE',
    PROMOTE_GRAY_PREPROD: 'PROMOTE_GRAY_PREPROD',
    PROMOTE_GRAY_ONLINE: 'PROMOTE_GRAY_ONLINE',
} as const;
const statusColor = (status?: string): string => {
    if (status === 'SUCCEEDED' || status === 'PUBLISHED' || status === 'PASSED')
        return 'success';
    if (status === 'FAILED' || status === 'PARTIAL_FAILED' || status === 'PARTIAL_FAILURE') {
        return 'error';
    }
    if (status === 'REJECTED' || status === 'STALE')
        return 'error';
    if (status === 'USED')
        return 'success';
    if (isPendingReleaseOperationStatus(status) || status === 'EXPIRED')
        return 'warning';
    if (status === 'ACTIVE')
        return 'processing';
    return 'default';
};
const formatTime = (time?: number): string => time ? new Date(time).toLocaleString('zh-CN', { hour12: false }) : '-';
interface AssetReleaseTabProps {
    assetType: ReleaseAssetType;
    assetKey: string;
    title?: string;
    showCreateChange?: boolean;
    onOverviewChange?: (overview: AssetReleaseOverview) => void;
    onHistoricalDraftRestore?: () => void | Promise<void>;
}
const assetTypeLabel: Record<ReleaseAssetType, string> = {
    SKILL: 'Skill',
    COMPONENT: '组件',
    CAPABILITY_ACTION: '业务能力',
    ORCHESTRATION_CONFIG: 'Workflow',
    A2UI_CATALOG: 'A2UI Catalog',
    A2UI_APPLICATION: 'A2UI Application',
};
const statusLabel: Record<string, string> = {
    ACTIVE: '编辑中',
    SEALED: '已封板',
    SUCCEEDED: '成功',
    PUBLISHED: '已发布',
    FAILED: '失败',
    PARTIAL_FAILED: '部分失败',
    PARTIAL_FAILURE: '部分失败',
    PASSED: '通过',
    EXPIRED: '已过期',
    PUBLISHING: '发布中',
    PLATFORM_PENDING: '平台处理中',
    PREPARING: '准备提交',
    STALE: '内容已变化',
    USED: '已使用',
};
const sourceTypeLabel: Record<string, string> = {
    BUILD: '预发构建',
    VERSION: '正式版本',
};
interface GrayRuleInput {
    percentage: string;
    userIdWhitelist: string;
}
const initialGrayRuleInput = (): Record<ReleaseEnvironment, GrayRuleInput> => ({
    PRT: { percentage: '100', userIdWhitelist: '' },
    ONLINE: { percentage: '10', userIdWhitelist: '' },
});
const displayStatus = (status?: string): string => status ? statusLabel[status] || status : '暂无';
const displaySource = (sourceType?: string, sourceId?: string): string => {
    if (!sourceType)
        return '暂无成功部署';
    return `${sourceTypeLabel[sourceType] || sourceType}${sourceId ? ` · ${sourceId}` : ''}`;
};
const environmentInputDigest = (overview: AssetReleaseOverview | undefined, state: ReleaseEnvironmentState | undefined): string | undefined => {
    if (!state)
        return undefined;
    if (state.sourceType === 'BUILD') {
        return overview?.builds?.find((build) => build.buildId === state.sourceId)?.inputDigest;
    }
    return overview?.versions?.find((version) => version.versionId === state.sourceId)?.inputDigest;
};
/**
 * SkillFactory 内部资产详情页复用的发布控制面。
 *
 * 页面只渲染后端返回的 allowedActions，不在浏览器推断发布资格；线上发布和历史版本重发均要求
 * 二次确认。领域正文仍由各详情页维护，本组件只负责公共 Change/Build/Version/Deployment 流程。
 */
const AssetReleaseTabContent: React.FC<AssetReleaseTabProps> = ({ assetType, assetKey, title, showCreateChange = true, onOverviewChange, onHistoricalDraftRestore, }) => {
    const [overview, setOverview] = useState<AssetReleaseOverview>();
    const [diffDocument, setDiffDocument] = useState<ReleaseDiffDocument>();
    const [diffDetail, setDiffDetail] = useState<ReleaseDiffEntry>();
    const [selectedDiffPath, setSelectedDiffPath] = useState('');
    const [diffViewMode, setDiffViewMode] = useState<ReleaseDiffViewMode>('UNIFIED');
    const [diffContextLines, setDiffContextLines] = useState(3);
    const [baseVersion, setBaseVersion] = useState<number>();
    const [changeName, setChangeName] = useState('');
    const [compareVersion, setCompareVersion] = useState<number>();
    const [historyVersion, setHistoryVersion] = useState<number>();
    const [onlineSource, setOnlineSource] = useState<'CURRENT' | 'HISTORICAL'>('CURRENT');
    const [loading, setLoading] = useState(false);
    const [actionLoading, setActionLoading] = useState('');
    const [error, setError] = useState('');
    const [forceConfirmModalOpen, setForceConfirmModalOpen] = useState(false);
    const [forceReason, setForceReason] = useState('');
    const [grayRuleInput, setGrayRuleInput] = useState(initialGrayRuleInput);
    const { access, permissions, loading: accessLoading, error: accessError, readonlyReason, refresh: refreshAccess, } = useAssetAccessContext();
    const loadOverview = useCallback(async () => {
        if (!assetKey)
            return;
        setLoading(true);
        setError('');
        try {
            const result = await assetReleaseApi.overview(assetType, assetKey);
            setOverview(result);
            onOverviewChange?.(result);
            const firstVersion = result.versions?.[0]?.version;
            const latestVersion = (result.versions || []).reduce((latest, item) => Math.max(latest, item.version), 0) ||
                undefined;
            setBaseVersion((current) => current != null && (result.versions || []).some((item) => item.version === current)
                ? current
                : latestVersion);
            setCompareVersion((current) => current ?? firstVersion);
            setHistoryVersion((current) => current ?? firstVersion);
        }
        catch (e) {
            setError(e instanceof Error ? e.message : '发布状态加载失败');
        }
        finally {
            setLoading(false);
        }
    }, [assetKey, assetType, onOverviewChange]);
    useEffect(() => {
        loadOverview();
    }, [loadOverview]);
    useEffect(() => {
        setGrayRuleInput((current) => {
            const next = { ...current };
            (['PRT', 'ONLINE'] as const)?.forEach((environment) => {
                const rule = overview?.environments?.[environment]?.grayRule;
                if (rule) {
                    next[environment] = {
                        percentage: String(rule.percentage),
                        userIdWhitelist: (rule.userIdWhitelist || []).join(','),
                    };
                }
            });
            return next;
        });
    }, [overview?.environments]);
    const allowed = useMemo(() => new Set(overview?.allowedActions || []), [overview?.allowedActions]);
    const canCreateChange = permissions.canEdit && allowed.has(action.CREATE_CHANGE);
    const canPublishPreprod = permissions.canPublish && allowed.has(action.DEPLOY_PREPROD);
    const preprodButtonTitle = canPublishPreprod
        ? '发布到预发'
        : !permissions.canPublish
            ? readonlyReason || '当前用户没有发布权限'
            : assetType === 'CAPABILITY_ACTION'
                ? '要校验通过才能点发布'
                : overview?.blockedReasons?.[0] || '预发发布门禁未通过';
    const showCapabilityValidationHint = assetType === 'CAPABILITY_ACTION' && permissions.canPublish && !canPublishPreprod;
    const canPublishOnline = permissions.canPublish && allowed.has(action.DEPLOY_ONLINE);
    const canForcePublishOnline = permissions.canForcePublish && allowed.has(action.FORCE_DEPLOY_ONLINE);
    const canRedeployHistory = permissions.canPublish && allowed.has(action.REDEPLOY_HISTORY);
    const currentVersion = overview?.activeChange?.targetVersion;
    const currentDigest = overview?.currentSnapshot?.digest;
    const currentBuild = overview?.builds?.find((build) => build.status === 'SUCCEEDED' && (build.inputDigest || build.sourceDigest) === currentDigest);
    const currentReleaseDigest = currentBuild?.sourceDigest;
    const selectedHistory = overview?.versions?.find((version) => version.version === historyVersion);
    const canRunCurrentOnlineAction = canPublishOnline;
    const canRunHistoryAction = canRedeployHistory;
    const canRunForceAction = permissions.canForcePublish && onlineSource === "CURRENT" && canForcePublishOnline;
    const onlineActionLabel = onlineSource === "HISTORICAL" ? "\u91CD\u65B0\u53D1\u5E03\u5230\u7EBF\u4E0A" : "\u53D1\u5E03\u5230\u7EBF\u4E0A";
    const forceActionLabel = "\u5F3A\u5236\u53D1\u5E03\u5230\u7EBF\u4E0A";
    const forcePublishReason = !permissions.canForcePublish ? "\u4EC5\u7BA1\u7406\u5458\u53EF\u4EE5\u6267\u884C\u5F3A\u5236\u53D1\u5E03" : onlineSource !== "CURRENT" ? "\u8BF7\u5207\u6362\u5230\u5F53\u524D\u5185\u5BB9" : "\u4EC5\u7BA1\u7406\u5458\u53EF\u4EE5\u5FFD\u89C6\u51C6\u51FA\u7ED3\u679C\u5E76\u5F3A\u5236\u53D1\u5E03";
    const versionOptions = useMemo(() => [...(overview?.versions || [])]
        ?.sort((left, right) => right.version - left.version)
        ?.map?.((item) => ({
        label: String(item.version),
        value: item.version,
    })), [overview?.versions]);
    const run = async (key: string, operation: () => Promise<AssetReleaseOperationResult>): Promise<boolean> => {
        setActionLoading(key);
        try {
            const execution = await executeReleaseOperation(operation, () => assetReleaseApi.overview(assetType, assetKey));
            const { feedback } = execution;
            if (feedback.kind === 'SUCCESS') {
                message.success(feedback.message);
            }
            else if (feedback.kind === 'PENDING') {
                message.info(feedback.message);
            }
            else {
                message.error(feedback.message);
            }
            if (execution.overview) {
                setOverview(execution.overview);
                onOverviewChange?.(execution.overview);
            }
            if (execution.refreshError) {
                message.error('操作结果已返回，但发布状态刷新失败，请手动刷新');
            }
            return feedback.kind !== 'FAILURE';
        }
        catch (e) {
            message.error(e instanceof Error ? e.message : '发布操作失败');
            await refreshAccess();
            return false;
        }
        finally {
            setActionLoading('');
        }
    };
    const handleCreateChange = async () => {
        const normalizedName = changeName.trim();
        if (!normalizedName) {
            message.warning('请输入变更名称');
            return;
        }
        const created = await run(action.CREATE_CHANGE, () => assetReleaseApi.createChange(assetType, assetKey, baseVersion, normalizedName));
        if (created) {
            setChangeName('');
            if (baseVersion !== undefined) {
                setBaseVersion(undefined);
                await onHistoricalDraftRestore?.();
            }
        }
    };
    const handleDiff = async () => {
        setActionLoading('DIFF');
        try {
            const document = await assetReleaseApi.diff(assetType, assetKey, compareVersion, {
                viewMode: diffViewMode,
                contextLines: diffContextLines,
            });
            setDiffDocument(document);
            const firstPath = document.entries?.[0]?.path || '';
            setSelectedDiffPath(firstPath);
            if (firstPath) {
                const detail = await assetReleaseApi.diff(assetType, assetKey, compareVersion, {
                    entryPath: firstPath,
                    viewMode: diffViewMode,
                    contextLines: diffContextLines,
                });
                setDiffDetail(detail.entries?.[0]);
            }
            else {
                setDiffDetail(undefined);
            }
        }
        catch (e) {
            message.error(e instanceof Error ? e.message : 'Diff 查询失败');
        }
        finally {
            setActionLoading('');
        }
    };
    const loadDiffDetail = async (path: string, viewMode = diffViewMode, contextLines = diffContextLines) => {
        if (!path)
            return;
        setSelectedDiffPath(path);
        setActionLoading('DIFF_DETAIL');
        try {
            const detail = await assetReleaseApi.diff(assetType, assetKey, compareVersion, {
                entryPath: path,
                viewMode,
                contextLines,
            });
            setDiffDetail(detail.entries?.[0]);
        }
        catch (e) {
            message.error(e instanceof Error ? e.message : '文件 Diff 查询失败');
        }
        finally {
            setActionLoading('');
        }
    };
    const handleDiffViewModeChange = (viewMode: ReleaseDiffViewMode) => {
        setDiffViewMode(viewMode);
        if (selectedDiffPath) {
            loadDiffDetail(selectedDiffPath, viewMode, diffContextLines);
        }
    };
    const handleDiffContextLinesChange = (contextLines: number) => {
        setDiffContextLines(contextLines);
        if (selectedDiffPath) {
            loadDiffDetail(selectedDiffPath, diffViewMode, contextLines);
        }
    };
    const handlePreprod = () => {
        const digest = overview?.currentSnapshot?.digest;
        const version = overview?.activeChange?.targetVersion;
        if (!digest || !version)
            return;
        run(action.DEPLOY_PREPROD, () => assetReleaseApi.deployPreprod(assetType, assetKey, version, digest));
    };
    const handleOnline = () => {
        const digest = overview?.currentSnapshot?.digest;
        const version = overview?.activeChange?.targetVersion;
        if (!digest || !version)
            return;
        Modal.confirm({
            title: '发布到线上',
            content: `确认把 ${assetKey} 的当前预发 Build 封板并发布到线上？`,
            okText: '确认发布',
            cancelText: '取消',
            onOk: () => run(action.DEPLOY_ONLINE, () => assetReleaseApi.deployOnline(assetType, assetKey, version, digest, currentReleaseDigest)),
        });
    };
    const handleHistory = () => {
        if (!historyVersion)
            return;
        const selectedVersion = overview?.versions?.find((version) => version.version === historyVersion);
        if (!selectedVersion?.sourceDigest) {
            message.error('当前正式版本缺少摘要，无法生成幂等发布请求');
            return;
        }
        Modal.confirm({
            title: `重新发布版本 ${historyVersion}`,
            content: '历史版本重发不会创建新版本，但会改变线上环境当前内容。',
            okText: '确认重发',
            cancelText: '取消',
            onOk: () => run(action.REDEPLOY_HISTORY, () => assetReleaseApi.redeployHistory(assetType, assetKey, historyVersion, selectedVersion.sourceDigest)),
        });
    };
    const handleForceOnline = () => {
        const digest = overview?.currentSnapshot?.digest;
        const version = overview?.activeChange?.targetVersion;
        if (!digest || !version)
            return;
        Modal.confirm({
            title: '忽视准出结果强制发布',
            content: `确认忽视 ${assetKey} 当前未通过的准出结果并发布到线上？`,
            okText: '确认强制发布',
            cancelText: '取消',
            okButtonProps: { danger: true },
            onOk: () => run(action.FORCE_DEPLOY_ONLINE, () => assetReleaseApi.forceDeployOnline(assetType, assetKey, version, digest, currentReleaseDigest, forceReason.trim())),
        });
    };
    const handleOnlineSourcePublish = () => { if (onlineSource === "HISTORICAL")
        handleHistory();
    else
        handleOnline(); };
    const handleForceAction = () => { setForceReason(""); setForceConfirmModalOpen(true); };
    const handleForceConfirmSubmit = () => { if (!currentVersion || !currentDigest || !forceReason.trim()) {
        message.warning("\u8BF7\u586B\u5199\u5F3A\u5236\u53D1\u5E03\u539F\u56E0");
        return;
    } setForceConfirmModalOpen(false); handleForceOnline(); };
    const updateGrayRuleInput = (environment: ReleaseEnvironment, field: keyof GrayRuleInput, value: string) => {
        setGrayRuleInput((current) => ({
            ...current,
            [environment]: { ...current[environment], [field]: value },
        }));
    };
    const normalizedGrayRule = (environment: ReleaseEnvironment) => {
        const percentage = Number(grayRuleInput[environment]?.percentage);
        if (!Number.isInteger(percentage) || percentage < 0 || percentage > 100) {
            message.warning('灰度比例必须是 0 到 100 的整数');
            return undefined;
        }
        const userIdWhitelist = normalizeUserIdWhitelist(grayRuleInput[environment]?.userIdWhitelist);
        if (userIdWhitelist === undefined) {
            message.warning('userId 白名单须为 signed64 范围内的规范十进制整数，多个值用英文逗号分隔');
            return undefined;
        }
        return { percentage, userIdWhitelist };
    };
    const handleGrayStart = async (environment: ReleaseEnvironment) => {
        const digest = overview?.currentSnapshot?.digest;
        const version = overview?.activeChange?.targetVersion;
        if (!digest || !version) {
            message.warning('缺少当前变更或内容摘要，无法开始灰度');
            return;
        }
        const rule = normalizedGrayRule(environment);
        if (!rule)
            return;
        const startAction = environment === 'PRT' ? action.START_GRAY_PREPROD : action.START_GRAY_ONLINE;
        if (!allowed.has(startAction))
            return;
        await run(startAction, () => assetReleaseApi.startGray(assetType, assetKey, environment, version, digest, rule.percentage, rule.userIdWhitelist));
    };
    const executeGrayMutation = async (environment: ReleaseEnvironment, mutation: 'ADJUST' | 'STOP' | 'PROMOTE') => {
        const candidate = overview?.environments?.[environment]?.candidate;
        if (!candidate?.sourceId || !candidate.digest) {
            message.warning('当前候选版本不存在，请刷新后重试');
            return;
        }
        const rule = mutation === 'ADJUST' ? normalizedGrayRule(environment) : undefined;
        if (mutation === 'ADJUST' && !rule)
            return;
        const method: 'RELEASE_GRAY_ADJUST' | 'RELEASE_GRAY_STOP' | 'RELEASE_GRAY_PROMOTE' = mutation === 'ADJUST'
            ? 'RELEASE_GRAY_ADJUST'
            : mutation === 'STOP'
                ? 'RELEASE_GRAY_STOP'
                : 'RELEASE_GRAY_PROMOTE';
        const operation = () => assetReleaseApi.mutateGray(method, assetType, assetKey, environment, candidate.sourceId, candidate.digest, rule?.percentage, rule?.userIdWhitelist);
        await run(`${mutation}_${environment}`, operation);
    };
    const handleGrayMutation = (environment: ReleaseEnvironment, mutation: 'ADJUST' | 'STOP' | 'PROMOTE') => {
        if (mutation === 'ADJUST') {
            executeGrayMutation(environment, mutation);
            return;
        }
        Modal.confirm({
            title: mutation === 'STOP' ? '停止灰度' : '转为全量',
            content: mutation === 'STOP'
                ? '停止后将清除候选版本和灰度规则，稳定版本保持不变。'
                : '确认把当前候选版本提升为稳定版本并结束本轮灰度？',
            okText: mutation === 'STOP' ? '确认停止' : '确认转全量',
            cancelText: '取消',
            onOk: () => executeGrayMutation(environment, mutation),
        });
    };
    const snapshotSummary = overview?.currentSnapshot?.summary || {};
    const isSkill = assetType === 'SKILL';
    const renderGrayReleasePanel = (environment: ReleaseEnvironment): React.ReactNode => {
        const state = overview?.environments?.[environment];
        const candidate = state?.candidate;
        const startAction = environment === 'PRT' ? action.START_GRAY_PREPROD : action.START_GRAY_ONLINE;
        const adjustAction = environment === 'PRT' ? action.ADJUST_GRAY_PREPROD : action.ADJUST_GRAY_ONLINE;
        const stopAction = environment === 'PRT' ? action.STOP_GRAY_PREPROD : action.STOP_GRAY_ONLINE;
        const promoteAction = environment === 'PRT' ? action.PROMOTE_GRAY_PREPROD : action.PROMOTE_GRAY_ONLINE;
        const canStart = permissions.canPublish && allowed.has(startAction);
        const startLabel = `开始${environment === "PRT" ? "\u9884\u53D1" : "\u7EBF\u4E0A"}灰度`;
        return (<div className={`asset-release-gray-environment ${environment.toLowerCase()}`}>
        <div className="asset-release-environment-title">
          <div>
            <strong>账号灰度</strong>
            <Text type="secondary">白名单优先于比例</Text>
          </div>
          <Tag color={candidate ? 'processing' : 'default'}>{candidate ? '灰度中' : '稳定'}</Tag>
        </div>
        <div className="asset-release-gray-version-grid">
          <div className="asset-release-gray-version-item">
            <Text type="secondary">稳定版本</Text>
            <strong>
              {displaySource(state?.sourceType, state?.sourceId)} · 版本 {state?.version ?? '-'}
            </strong>
          </div>
          <div className="asset-release-gray-version-item">
            <Text type="secondary">候选版本</Text>
            <strong>
              {candidate
                ? `${displaySource(candidate.sourceType, candidate.sourceId)} · 版本 ${candidate.version ?? '-'}`
                : '暂无'}
            </strong>
          </div>
        </div>
        <div className="asset-release-gray-rule">
          <Input disabled={!permissions.canPublish} maxLength={3} placeholder="比例 0-100" value={grayRuleInput[environment]?.percentage} onChange={(event) => updateGrayRuleInput(environment, 'percentage', event.target.value)}/>
          <Input disabled={!permissions.canPublish} placeholder="userId 白名单，英文逗号分隔" value={grayRuleInput[environment]?.userIdWhitelist} onChange={(event) => updateGrayRuleInput(environment, 'userIdWhitelist', event.target.value)}/>
        </div>
        {Number(grayRuleInput[environment]?.percentage) === 100 ? (<Alert type="warning" showIcon message="全部账号将命中候选版本，仍需手动转全量"/>) : null}
        {null}
        <Space wrap className="asset-release-gray-actions">
          {!candidate ? (<Button type="primary" disabled={!canStart} loading={actionLoading === startAction} onClick={() => handleGrayStart(environment)}>
              {startLabel}
            </Button>) : (<>
              <Button disabled={!permissions.canPublish || !allowed.has(adjustAction)} loading={actionLoading === `ADJUST_${environment}`} onClick={() => handleGrayMutation(environment, 'ADJUST')}>
                调整规则
              </Button>
              <Button danger disabled={!permissions.canPublish || !allowed.has(stopAction)} loading={actionLoading === `STOP_${environment}`} onClick={() => handleGrayMutation(environment, 'STOP')}>
                停止灰度
              </Button>
              <Button type="primary" disabled={!permissions.canPublish || !allowed.has(promoteAction)} loading={actionLoading === `PROMOTE_${environment}`} onClick={() => handleGrayMutation(environment, 'PROMOTE')}>
                转全量
              </Button>
            </>)}
        </Space>
      </div>);
    };
    if (!assetKey) {
        return <Empty description="缺少发布资产标识"/>;
    }
    return (<Spin spinning={loading || accessLoading}>
      <div className="asset-release-tab">
        <div className="asset-release-toolbar">
          <div>
            <h2>{title || '发布管理'}</h2>
            {assetType !== 'CAPABILITY_ACTION' ? (<Text type="secondary">
                {assetTypeLabel[assetType]}标识：<Text code>{assetKey}</Text>
              </Text>) : null}
          </div>
          <Space>
            <AssetOwnerManagement assetType={assetType} assetKey={assetKey} access={access} onAccessRefresh={refreshAccess}/>
            <Button icon={<ReloadOutlined />} onClick={async () => {
            await Promise.all([loadOverview(), refreshAccess()]);
        }}>
              刷新
            </Button>
          </Space>
        </div>

        {error ? <Alert type="error" showIcon message={error}/> : null}
        {accessError ? <Alert type="error" showIcon message={accessError}/> : null}
        {!accessLoading && !permissions.canEdit ? (<Alert type="warning" showIcon message={readonlyReason || '当前资产仅可查看'}/>) : null}
        <div className="asset-release-environments compact">
          {(['PRT', 'ONLINE'] as const)?.map((environment) => {
            const state = overview?.environments?.[environment];
            const contentDigest = environmentInputDigest(overview, state);
            return (<div className={`asset-release-environment ${environment.toLowerCase()}`} key={environment}>
                <div className="asset-release-environment-title">
                  <strong>{environment === 'PRT' ? '预发环境' : '线上环境'}</strong>
                  <Tag color={state ? 'success' : 'default'}>{state ? '已部署' : '未部署'}</Tag>
                </div>
                <Space wrap>
                  <Text type="secondary">{displaySource(state?.sourceType, state?.sourceId)}</Text>
                  <Text>版本 {state?.version ?? '-'}</Text>
                  <Text type="secondary">内容摘要</Text>
                  <Text code title={contentDigest}>
                    {contentDigest?.slice(0, 12) || '-'}
                  </Text>
                  <Text type="secondary">{formatTime(state?.updateTime)}</Text>
                </Space>
              </div>);
        })}
        </div>

        <div className="asset-release-content-grid">
          <Card title="发布流程" className="asset-release-operation-card">
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="目标版本">
                {overview?.activeChange?.targetVersion ?? overview?.nextVersion ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label="变更名称">
                {overview?.activeChange?.changeName || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="变更状态">
                <Tag color={statusColor(overview?.activeChange?.status)}>
                  {overview?.activeChange
            ? displayStatus(overview.activeChange?.status)
            : '未新建变更'}
                </Tag>
              </Descriptions.Item>
              {isSkill ? (<>
                  <Descriptions.Item label="Skill 包">
                    {String(snapshotSummary.skillCode || assetKey)}
                  </Descriptions.Item>
                </>) : null}
              <Descriptions.Item label="当前内容摘要" span={2}>
                <Text code>{overview?.currentSnapshot?.digest || '-'}</Text>
              </Descriptions.Item>
            </Descriptions>

            {showCreateChange ? (<Space wrap className="asset-release-actions">
                <Select allowClear disabled={!canCreateChange} options={versionOptions} placeholder="来源版本（选择后恢复）" style={{ width: 180 }} value={baseVersion} onChange={(value) => setBaseVersion(value as number | undefined)}/>
                <Input maxLength={80} placeholder="变更名称" style={{ width: 220 }} value={changeName} onChange={(event) => setChangeName(event.target.value)}/>
                <Button icon={<PlusOutlined />} disabled={!canCreateChange || !changeName.trim()} title={!canCreateChange
                ? readonlyReason
                : changeName.trim()
                    ? '新建变更'
                    : '请先填写变更名称'} loading={actionLoading === action.CREATE_CHANGE} onClick={handleCreateChange}>
                  {baseVersion === undefined ? '新建变更' : '恢复并新建变更'}
                </Button>
              </Space>) : null}

            {overview?.grayReleaseSupported ? (<Alert className="asset-release-gray-guidance" type="info" showIcon message="账号灰度按 userId 白名单和比例路由；比例达到 100% 后仍需手动转全量"/>) : null}

            <div className="asset-release-flow-step">
              <div className="asset-release-flow-primary">
                <div>
                  <strong>发布到预发</strong>
                  <p>
                    {isSkill
            ? '冻结当前工作区并发布到预发环境。'
            : '冻结当前内容并部署到预发环境。'}
                  </p>
                </div>
                <div className="asset-release-primary-action">
                  <Button type="primary" icon={<CloudUploadOutlined />} disabled={!canPublishPreprod} title={preprodButtonTitle} loading={actionLoading === action.DEPLOY_PREPROD} onClick={handlePreprod}>
                    发布到预发
                  </Button>
                  {showCapabilityValidationHint ? (<Text type="danger">要校验通过才能点发布</Text>) : null}
                </div>
              </div>
              {overview?.grayReleaseSupported ? renderGrayReleasePanel('PRT') : null}
            </div>

            <div className="asset-release-flow-step">
              <div className="asset-release-flow-primary">
                <div>
                  <strong>发布到线上</strong>
                  <p>
                    {isSkill
            ? '当前内容原样封板，历史版本复用不可变 ZIP；线上发布要求文件摘要具备有效准出证据。'
            : '选择当前内容封板，或重新部署一个历史正式版本。'}
                  </p>
                  <Space wrap>
                    <Select value={onlineSource} style={{ width: 132 }} options={[
            { label: '当前内容', value: 'CURRENT' },
            { label: '历史版本', value: 'HISTORICAL' },
        ]} onChange={(value) => setOnlineSource(value as 'CURRENT' | 'HISTORICAL')}/>
                    {onlineSource === 'HISTORICAL' ? (<Select options={versionOptions} placeholder="选择版本" style={{ width: 120 }} value={historyVersion} onChange={(value) => setHistoryVersion(value as number)}/>) : null}
                  </Space>
                </div>
                <div className="asset-release-online-actions">
                  <Button type="primary" icon={<CloudUploadOutlined />} disabled={onlineSource === 'CURRENT'
            ? !canRunCurrentOnlineAction
            : !canRunHistoryAction || !historyVersion} title={onlineSource === 'CURRENT'
            ? canRunCurrentOnlineAction
                ? onlineActionLabel
                : readonlyReason
            : canRunHistoryAction
                ? onlineActionLabel
                : readonlyReason} loading={actionLoading === action.DEPLOY_ONLINE ||
            actionLoading === action.REDEPLOY_HISTORY} onClick={handleOnlineSourcePublish}>
                    {onlineActionLabel}
                  </Button>
                  <Button danger disabled={!canRunForceAction} title={forcePublishReason} loading={actionLoading === action.FORCE_DEPLOY_ONLINE} onClick={handleForceAction}>
                    {forceActionLabel}
                  </Button>
                </div>
              </div>
              {overview?.grayReleaseSupported ? renderGrayReleasePanel('ONLINE') : null}
            </div>
          </Card>

          <Card title="发布检查" className="asset-release-detail-card">
            {(['PRT', 'ONLINE'] as const).map((environment) => {
            const gates = overview?.environmentGates?.[environment]
                ?? (environment === 'PRT' ? overview?.gates : undefined);
            const label = environment === 'PRT' ? '预发' : '线上';
            return (<div key={environment} style={{ marginBottom: 16 }}>
                  <h4>{label}检查</h4>
                  <div className="asset-release-list">
                    {(gates || []).map((gate) => (<div className="asset-release-list-item" key={gate.code}>
                        <Tag color={statusColor(gate.status)}>{displayStatus(gate.status)}</Tag>
                        <div>
                          <strong>{releaseGateLabel(gate.code, gate.label)}{gate.required ? '（必选）' : ''}</strong>
                          <p>{gate.message}</p>
                          {gate.required && gate.status !== 'PASSED' ? (<p>{releaseGateNextStep(gate.code)}</p>) : null}
                        </div>
                      </div>))}
                    {!gates?.length ? (<Alert type="info" showIcon message={`尚未取得${label}检查结果`} description={environment === 'ONLINE'
                        ? '先将当前内容成功发布到预发，再点击刷新。已有成功预发版本仍无结果时，请联系平台排查；预发检查通过不代表线上检查通过。'
                        : '请点击刷新获取检查结果；仍无结果时，请联系平台排查。'}/>) : null}
                  </div>
                </div>);
        })}
            {overview?.blockedReasons?.length ? (<Alert type="warning" showIcon message="暂时无法发布的原因" description={overview.blockedReasons?.join?.('；')}/>) : null}
          </Card>
        </div>

        {null}

        <Card title="版本、Diff 与发布流水" className="asset-release-detail-card">
          <div className="asset-release-subheading">
            <strong>正式版本</strong>
            <Space wrap>
              <Select options={versionOptions} placeholder="对比版本" style={{ width: 128 }} value={compareVersion} onChange={(value) => {
            setCompareVersion(value as number);
            setDiffDocument(undefined);
            setDiffDetail(undefined);
            setSelectedDiffPath('');
        }}/>
              <Button disabled={!versionOptions.length} loading={actionLoading === 'DIFF'} onClick={handleDiff}>
                查看 Diff
              </Button>
            </Space>
          </div>
          <div className="asset-release-version-strip">
            {(overview?.versions || []).map((version) => (<div className="asset-release-version-item" key={version.versionId}>
                <Tag color="blue">{version.version}</Tag>
                <div>
                  <strong>{version.sourceBuildId}</strong>
                  <p>
                    {version.sourceDigest} · {version.operator} · {formatTime(version.createTime)}
                  </p>
                </div>
              </div>))}
            {!overview?.versions?.length ? <Empty description="暂无正式版本"/> : null}
          </div>
          <ReleaseDiffViewer contextLines={diffContextLines} detailEntry={diffDetail} detailLoading={actionLoading === 'DIFF_DETAIL'} document={diffDocument} loading={actionLoading === 'DIFF'} selectedPath={selectedDiffPath} viewMode={diffViewMode} onContextLinesChange={handleDiffContextLinesChange} onEntrySelect={loadDiffDetail} onViewModeChange={handleDiffViewModeChange}/>
        </Card>

        <Card title="最近发布流水" className="asset-release-detail-card">
          <div className="asset-release-list">
            {(overview?.deployments || []).slice(0, 10).map((deployment) => (<div className="asset-release-list-item" key={deployment.deploymentId}>
                <Tag color={statusColor(deployment.status)}>{displayStatus(deployment.status)}</Tag>
                <div>
                  <strong>
                    {deployment.environment === 'PRT' ? '预发' : '线上'} ·{' '}
                    {sourceTypeLabel[deployment.sourceType] || deployment.sourceType} ·{' '}
                    {deployment.sourceVersion ?? '-'}
                    {deployment.forced ? ' · 管理员强制' : ''}
                  </strong>
                  <p>
                    {deployment.message || '-'} · {deployment.operator} ·{' '}
                    {formatTime(deployment.createTime)}
                  </p>
                </div>
              </div>))}
            {!overview?.deployments?.length ? <Empty description="暂无发布流水"/> : null}
          </div>
        </Card>
        <Modal title={'强制发布确认'} visible={forceConfirmModalOpen} okText={'继续强制发布'} cancelText="取消" confirmLoading={actionLoading === action.FORCE_DEPLOY_ONLINE} okButtonProps={{ danger: true, disabled: !forceReason.trim() }} onCancel={() => setForceConfirmModalOpen(false)} onOk={handleForceConfirmSubmit}>
          <Text type="secondary">
            {'请说明忽视当前准出结果的原因。该原因会记录到本次发布流水。'}
          </Text>
          <Input.TextArea autoFocus maxLength={500} placeholder="请输入强制发布原因" rows={4} value={forceReason} onChange={(event) => setForceReason(event.target.value)}/>
        </Modal>
      </div>
    </Spin>);
};
const AssetReleaseTab: React.FC<AssetReleaseTabProps> = (props) => (<AssetAccessProvider assetType={props.assetType} assetKey={props.assetKey}>
    <AssetReleaseTabContent {...props}/>
  </AssetAccessProvider>);
function releaseGateLabel(code: string, fallback: string): string {
    const labels: Record<string, string> = {
        A2UI_APPLICATION_SOURCE_DIGEST: '应用内容已保存并固定',
        A2UI_APPLICATION_INLINE_MANIFEST: '发布所需的组件和动作已生成',
        A2UI_APPLICATION_CATALOG_ENVIRONMENT: '目标环境的组件库版本匹配',
    };
    return labels[code] || fallback;
}
function releaseGateNextStep(code: string): string {
    const steps: Record<string, string> = {
        A2UI_APPLICATION_SOURCE_DIGEST: '下一步：保存当前编排，再刷新检查结果。',
        A2UI_APPLICATION_INLINE_MANIFEST: '下一步：根据上方具体原因修复编排或依赖；若预发已成功但线上仍失败，请联系平台排查发布产物校验。',
        A2UI_APPLICATION_CATALOG_ENVIRONMENT: '下一步：确认该应用绑定的组件库精确版本已发布到目标环境，再刷新检查结果。',
    };
    return steps[code] || '下一步：按检查原因处理后刷新；无法自行处理时，将检查名称和原因提供给平台排查。';
}
export default AssetReleaseTab;
