import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Card, Input, Modal, Space, Spin, Tag, Typography, message } from 'antd';
import { a2uiApplicationApi, type A2uiPrtPreviewResult } from './api';
import type { A2uiLocalActionEvent } from './a2uiApplicationLocalPreview';
import A2uiApplicationRendererPreview from './A2uiApplicationRendererPreview';
import JsonFormatTextArea from './shared/JsonFormatTextArea';
import { jsonStringify } from './shared/safeJson';

const { Text } = Typography;
const POSITIVE_INT64 = /^[1-9][0-9]{0,18}$/;

function requestId(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  const suffix = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `m-prt-${Date.now().toString(36)}-${suffix}`;
}

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}

function isUnknownOutcome(reason: unknown): boolean {
  return errorMessage(reason, '').includes('A2UI_PRT_PREVIEW_OUTCOME_UNKNOWN');
}

function parseObject(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error('Application params 必须是 JSON object');
  }
  return parsed as Record<string, unknown>;
}

function releaseLabel(result: A2uiPrtPreviewResult): string {
  return `${result.release.sourceId} · ${result.release.appBuildId} · ${result.release.digest}`;
}

interface Props {
  applicationId?: string;
  defaultParamsJson: string;
}

const A2uiApplicationPrtPreview: React.FC<Props> = ({ applicationId, defaultParamsJson }) => {
  const [targetUserId, setTargetUserId] = useState('');
  const [paramsJson, setParamsJson] = useState(defaultParamsJson);
  const [result, setResult] = useState<A2uiPrtPreviewResult>();
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState('');
  const [outcomeUnknown, setOutcomeUnknown] = useState(false);
  const [composerDraft, setComposerDraft] = useState('');
  const consumedEffects = useRef(new Set<string>());
  const sessionIdRef = useRef<string>();
  const generationRef = useRef(0);
  const inFlightRef = useRef(false);
  const confirmOpenRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    sessionIdRef.current = result?.sessionId;
  }, [result?.sessionId]);

  useEffect(() => () => {
    mountedRef.current = false;
    generationRef.current += 1;
    const sessionId = sessionIdRef.current;
    sessionIdRef.current = undefined;
    if (sessionId) void a2uiApplicationApi.closePrtPreview(sessionId).catch(() => undefined);
  }, []);

  const validTargetUserId = useMemo(() => {
    if (!POSITIVE_INT64.test(targetUserId)) return false;
    try {
      return BigInt(targetUserId) <= 9223372036854775807n;
    } catch {
      return false;
    }
  }, [targetUserId]);

  const consumeEffects = useCallback((next: A2uiPrtPreviewResult) => {
    next.composerDraftEffects.forEach((effect) => {
      if (effect.type !== 'COMPOSER_DRAFT' || effect.mode !== 'APPEND'
          || consumedEffects.current.has(effect.requestId)) return;
      consumedEffects.current.add(effect.requestId);
      setComposerDraft((current) => current ? `${current}\n${effect.text}` : effect.text);
    });
  }, []);

  const start = useCallback(async () => {
    if (inFlightRef.current || result) return;
    if (!applicationId) {
      message.error('请先保存 Application，再启动 PRT 真实联调');
      return;
    }
    if (!validTargetUserId) {
      message.error('userId 必须是正 int64 十进制字符串');
      return;
    }
    let params: Record<string, unknown>;
    try {
      params = parseObject(paramsJson);
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : 'Application params 无效');
      return;
    }
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    inFlightRef.current = true;
    setLoading(true);
    setFailure('');
    setOutcomeUnknown(false);
    consumedEffects.current.clear();
    try {
      const next = await a2uiApplicationApi.startPrtPreview(
        applicationId,
        targetUserId,
        params,
        requestId(),
      );
      if (!mountedRef.current || generationRef.current !== generation) {
        void a2uiApplicationApi.closePrtPreview(next.sessionId).catch(() => undefined);
        return;
      }
      sessionIdRef.current = next.sessionId;
      setResult(next);
      consumeEffects(next);
    } catch (reason) {
      if (mountedRef.current && generationRef.current === generation) {
        setFailure(errorMessage(reason, 'PRT 启动失败'));
        setOutcomeUnknown(isUnknownOutcome(reason));
      }
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current && generationRef.current === generation) setLoading(false);
    }
  }, [applicationId, consumeEffects, paramsJson, result, targetUserId, validTargetUserId]);

  const close = useCallback(() => {
    if (inFlightRef.current) return;
    generationRef.current += 1;
    const sessionId = sessionIdRef.current;
    sessionIdRef.current = undefined;
    confirmOpenRef.current = false;
    setResult(undefined);
    setFailure('');
    setOutcomeUnknown(false);
    consumedEffects.current.clear();
    if (sessionId) void a2uiApplicationApi.closePrtPreview(sessionId).catch(() => undefined);
  }, []);

  const executeConfirmedAction = useCallback(async (
    event: A2uiLocalActionEvent,
    actionRequestId: string,
  ) => {
    if (!result || inFlightRef.current) return;
    const generation = generationRef.current;
    inFlightRef.current = true;
    setLoading(true);
    setFailure('');
    try {
      const next = await a2uiApplicationApi.executePrtPreviewAction({
        sessionId: result.sessionId,
        actionName: event.name,
        surfaceId: event.surfaceId,
        sourceComponentId: event.sourceComponentId,
        context: event.context || {},
        requestId: actionRequestId,
        confirmed: true,
      });
      if (!mountedRef.current || generationRef.current !== generation) {
        void a2uiApplicationApi.closePrtPreview(next.sessionId).catch(() => undefined);
        return;
      }
      setResult(next);
      consumeEffects(next);
    } catch (reason) {
      if (mountedRef.current && generationRef.current === generation) {
        const unknown = isUnknownOutcome(reason);
        setOutcomeUnknown(unknown);
        setFailure(unknown
          ? `${errorMessage(reason, 'PRT Action 结果未知')}；requestId=${actionRequestId}。不会自动重试，请先核对业务结果。`
          : errorMessage(reason, 'PRT Action 执行失败'));
      }
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current && generationRef.current === generation) setLoading(false);
    }
  }, [consumeEffects, result]);

  const handleAction = useCallback((event: A2uiLocalActionEvent) => {
    if (!result || inFlightRef.current || confirmOpenRef.current || outcomeUnknown) {
      if (outcomeUnknown) message.error('当前会话已因未知结果锁定，不能继续执行 Action');
      return;
    }
    const actionRequestId = requestId();
    confirmOpenRef.current = true;
    Modal.confirm({
      title: '确认执行真实 PRT Action',
      okText: '确认执行',
      cancelText: '取消',
      content: (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Text>target userId：{result.targetUserId}</Text>
          <Text>Action：{event.name}</Text>
          <Text type="secondary">以下是 Action 提交 context；最终 RPC 参数由已发布 requestMappings 与可信上下文生成。</Text>
          <pre style={{ maxHeight: 240, overflow: 'auto', margin: 0 }}>
            {jsonStringify(event.context || {}, null, 2)}
          </pre>
        </Space>
      ),
      onOk: () => {
        confirmOpenRef.current = false;
        return executeConfirmedAction(event, actionRequestId);
      },
      onCancel: () => { confirmOpenRef.current = false; },
    });
  }, [executeConfirmedAction, outcomeUnknown, result]);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="warning"
        showIcon
        message="PRT 真实联调会执行已发布 LoadBinding 和 CapabilityAction"
        description="只允许管理员启动；userId 必须手动填写。环境固定 PRT、客户端固定 PC，不会写入 Application，也不会发送聊天消息。"
      />
      {!applicationId ? <Alert type="error" message="未保存的 Application 不能执行 PRT 联调" /> : null}
      <Card size="small" title="PRT 执行输入">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <label>
            <Text strong>target userId（必填，正 int64）</Text>
            <Input
              value={targetUserId}
              onChange={(event) => setTargetUserId(event.target.value.trim())}
              placeholder="例如 101"
              status={targetUserId && !validTargetUserId ? 'error' : undefined}
              disabled={loading || Boolean(result)}
            />
          </label>
          <label>
            <Text strong>Application params JSON</Text>
            <JsonFormatTextArea
              value={paramsJson}
              onChange={(event) => setParamsJson(event.target.value)}
              onValueChange={setParamsJson}
              autoSize={{ minRows: 5, maxRows: 14 }}
              disabled={loading || Boolean(result)}
            />
          </label>
          <Space>
            <Button type="primary" onClick={start} loading={loading} disabled={!applicationId || Boolean(result)}>
              启动 PRT 真实联调
            </Button>
            <Button onClick={() => setParamsJson(defaultParamsJson)} disabled={loading || Boolean(result)}>
              重置参数样例
            </Button>
            {result ? <Button danger onClick={close} disabled={loading}>结束联调</Button> : null}
          </Space>
        </Space>
      </Card>
      {failure ? (
        <Alert
          type="error"
          showIcon
          message={outcomeUnknown ? 'PRT 联调结果未知，会话已锁定' : 'PRT 联调请求失败'}
          description={failure}
        />
      ) : null}
      <Spin spinning={loading}>
        {result ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card size="small" title="当前 PRT 发布身份">
              <Space wrap>
                <Tag color="blue">PRT</Tag>
                <Tag>{result.appCode}</Tag>
                <Tag>{result.catalog.catalogId}@{result.catalog.catalogRevision}</Tag>
                <Tag color={result.businessSuccess ? 'success' : 'warning'}>
                  businessSuccess={String(result.businessSuccess)}
                </Tag>
              </Space>
              <pre style={{ whiteSpace: 'pre-wrap', margin: '12px 0 0' }}>{releaseLabel(result)}</pre>
              {result.executions.some((execution) => !execution.success) ? (
                <Alert
                  type="warning"
                  showIcon
                  message="本次执行包含失败的 CapabilityAction"
                  description={result.executions
                    .filter((execution) => !execution.success)
                    .map((execution) => `${execution.actionCode}: ${execution.errorCode || 'businessSuccess=false'}`)
                    .join('；')}
                  style={{ marginTop: 12 }}
                />
              ) : null}
            </Card>
            <Card size="small" title="PRT A2UI 真实执行结果">
              <A2uiApplicationRendererPreview
                catalogId={result.catalog.catalogId}
                messages={result.messages}
                onAction={handleAction}
                footerText="PRT 真实联调：所有 Action 均需显式确认"
              />
            </Card>
            <Card size="small" title="M 测试输入框（仅回填，不发送）">
              <Input.TextArea
                value={composerDraft}
                onChange={(event) => setComposerDraft(event.target.value)}
                autoSize={{ minRows: 4, maxRows: 12 }}
                placeholder="Action 返回的 COMPOSER_DRAFT/APPEND 会按 requestId 去重后追加到这里"
              />
            </Card>
          </Space>
        ) : null}
      </Spin>
    </Space>
  );
};

export default A2uiApplicationPrtPreview;
