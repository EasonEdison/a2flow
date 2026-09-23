import React, { useEffect, useMemo, useRef, useState } from 'react';
import { MANAGEMENT_AI_PAUSE_REASON } from '../managementAuthoringPolicy';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remend from 'remend';
import { Button, Card, Space, Tag, Typography, Input, message, Select } from 'antd';
import { CheckOutlined, DownOutlined, StopOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { jsonParse, jsonStringify } from '../safeJson';
import { skillFactorySseTransport } from './transport';
import {
  isActiveCodingRun,
  isTerminalCodingRunEvent,
  latestUnfinishedCodingRun,
  skillFactoryApi,
} from '../../api';
import type {
  AuthoringChatTurn,
  AuthoringGuideConfig,
  AuthoringGuidePrompt,
  AuthoringSessionHistory,
  AuthoringSessionScopeParams,
  AuthoringSessionSummary,
  SkillFactoryCodingEvent,
  SkillFactoryRunStatus,
} from '../../api';
import type { SkillFactoryAuthoringTransport } from './transport';
import type { ChangeReviewStatus } from '../authoringChangeReview';
import {
  isPatchDomainEvent as isPatchEvent,
  isPatchSettledEvent,
} from '../authoringChangeReview/patchProjection';
import { domainResultToolCallIds, shouldDisplayGenericToolResult } from './toolResultProjection';
import {
  authoringSessionActorLabel,
  authoringTurnActorLabel,
  authoringTurnAvatarLabel,
  reconcilePersistedTurnAttribution,
} from './operatorPresentation';
import { recoverCodingRunAfterTransportEof } from './runRecovery';

export type { AuthoringGuideConfig, AuthoringGuidePrompt } from '../../api';

const { Text } = Typography;
const { TextArea } = Input;

type ChatTurnRole = 'user' | 'assistant';
type AssistantMessageStatus = 'streaming' | 'done' | 'cancelled' | 'error';

const STREAM_MODEL_CONTENT_EVENT_TYPE = 'MODEL_CONTENT_DELTA';
const STREAM_THINKING_EVENT_TYPE = 'THINK_TEXT_DELTA';
const STREAM_EVENT_TOOL_CALL_STARTED = 'TOOL_CALL_STARTED';
const STREAM_EVENT_TOOL_CALL_FINISHED = 'TOOL_CALL_FINISHED';
const STREAM_EVENT_RUN_COMPLETED = 'RUN_COMPLETED';
const STREAM_EVENT_RUN_FAILED = 'RUN_FAILED';
const STREAM_EVENT_RUN_CANCELLED = 'RUN_CANCELLED';
const STREAM_EVENT_TRANSPORT_RECOVERING = 'TRANSPORT_RECOVERING';
const LEGACY_EVENT_COMPLETED = 'COMPLETED';
const LEGACY_EVENT_FAILED = 'FAILED';
const DIAGNOSTIC_EVENT_ERROR = 'ERROR';
const STREAM_EVENT_ARTIFACT_CREATED = 'ARTIFACT_CREATED';
const AUTHORING_EVENT_BUSINESS_INTERACTION = 'BUSINESS_INTERACTION_CREATED';
const AUTHORING_EVENT_A2UI_MESSAGE = 'A2UI_MESSAGE';
const AUTHORING_EVENT_AG_UI = 'AG_UI_EVENT';
const AUTHORING_EVENT_OBSERVATION = 'AUTHORING_OBSERVATION';
const AUTHORING_EVENT_OBSERVATION_CREATED = 'OBSERVATION_CREATED';
const MODEL_CONTENT_TYPE_TEXT = 'TEXT';
const MODEL_CONTENT_TYPE_THINKING = 'THINKING';
const TRACE_STAGE_COLLAPSED_COUNT = 3;
const TRACE_DETAIL_MAX_LENGTH = 120;
const TRACE_RAW_DETAIL_MAX_LENGTH = 220;
const STREAM_RENDER_BATCH_MS = 50;
const CHAT_FOLLOW_BOTTOM_THRESHOLD = 24;
const GUIDE_ACTION_SEND = 'SEND';
const GUIDE_ACTION_FILL_INPUT = 'FILL_INPUT';
const GUIDE_TURN_ID_PREFIX = 'assistant-guide-';
const SESSION_TITLE_MAX_CHARACTERS = 10;
const AUTHORING_CHAT_CARD_BODY_STYLE: React.CSSProperties = {
  display: 'flex',
  minHeight: 0,
  flex: '1 1 0',
  flexDirection: 'column',
  overflow: 'hidden',
  padding: 0,
};

export interface SkillFactoryChatTurn {
  id: string;
  role: ChatTurnRole;
  text: string;
  timestamp: number;
  sessionId?: string;
  messageId?: string;
  operator?: string;
  optimistic?: boolean;
}

export interface SkillFactoryAuthoringMessage {
  messageId: string;
  sessionId?: string;
  runId?: string;
  timestamp: number;
  status: AssistantMessageStatus;
  answerText: string;
  events: SkillFactoryCodingEvent[];
  executionTrace: SkillFactoryCodingEvent[];
  businessEvents: SkillFactoryCodingEvent[];
}

export type SkillFactoryAuthoringChatItem =
  | { type: 'turn'; turn: SkillFactoryChatTurn }
  | { type: 'assistant'; message: SkillFactoryAuthoringMessage };

type OpenAuthoringReview = (changeSetId: string, event?: SkillFactoryCodingEvent) => void;

export interface SkillFactoryAuthoringDomainAdapter<TDraft = unknown> {
  domain: 'SKILL_CODING' | 'COMPONENT_CENTER' | 'CAPABILITY_CENTER' | 'A2UI_APPLICATION';
  sessionScope: AuthoringSessionScopeParams & { disabledReason?: string };
  buildRequest: (input: {
    message: string;
    sessionId?: string;
    messageId: string;
    runId: string;
    currentDraft?: TDraft;
  }) => Record<string, unknown>;
  isBusinessEventVisible?: (event: SkillFactoryCodingEvent) => boolean;
  onEvent?: (event: SkillFactoryCodingEvent) => void;
}

export interface UseSkillFactoryChatStreamOptions<TDraft = unknown> {
  adapter: SkillFactoryAuthoringDomainAdapter<TDraft>;
  transport?: SkillFactoryAuthoringTransport;
  workspaceId?: string;
  currentDraft?: TDraft;
}

export interface AuthoringSendOptions {
  displayText?: string;
  requestOverrides?: Record<string, unknown>;
}

export interface UseSkillFactoryChatStreamResult {
  input: string;
  setInput: React.Dispatch<React.SetStateAction<string>>;
  events: SkillFactoryCodingEvent[];
  turns: SkillFactoryChatTurn[];
  messages: SkillFactoryAuthoringMessage[];
  chatItems: SkillFactoryAuthoringChatItem[];
  renderRevision: number;
  loading: boolean;
  activeSessionId: string;
  selectedSessionId: string;
  sessionOptions: AuthoringSessionSummary[];
  authoringGuideConfig?: AuthoringGuideConfig;
  historyLoading: boolean;
  sessionDisabledReason?: string;
  selectSession: (sessionId: string) => Promise<void>;
  reloadHistory: (sessionId?: string) => Promise<void>;
  refreshSessionMetadata: (sessionId?: string) => Promise<void>;
  send: (messageText?: string, options?: AuthoringSendOptions) => Promise<void>;
  runGuidePrompt: (prompt: AuthoringGuidePrompt) => Promise<void>;
  stop: () => Promise<void>;
  appendEvent: (event: SkillFactoryCodingEvent) => void;
}

type HistoryApplyOptions = {
  replaceMessages?: boolean;
};

type HistoryReloadOptions = HistoryApplyOptions & {
  clearBeforeLoad?: boolean;
};

export type ExecutionTraceStageStatus = 'running' | 'done' | 'error';

export interface ExecutionTraceStage {
  key: string;
  label: string;
  title?: string;
  status: ExecutionTraceStageStatus;
  details: string[];
  rawDetail?: string;
  events: SkillFactoryCodingEvent[];
  timestamp?: number;
}

export interface ExecutionTraceRenderBlock {
  key: string;
  type: 'progress' | 'artifact';
  status?: ExecutionTraceStageStatus;
  event?: SkillFactoryCodingEvent;
  text?: string;
  stages?: ExecutionTraceStage[];
  timestamp?: number;
}

/**
 * 底层 Shell 仅用于历史 Skill 工作台过渡，新 Authoring Chat 场景必须使用 SkillFactoryAuthoringChat。
 */
export interface SkillFactoryAuthoringChatShellProps {
  title: React.ReactNode;
  extra?: React.ReactNode;
  listRef?: React.RefObject<HTMLDivElement>;
  listClassName?: string;
  messagesNode?: React.ReactNode;
  emptyText?: React.ReactNode;
  authoringGuideConfig?: AuthoringGuideConfig;
  onGuidePromptClick?: (prompt: AuthoringGuidePrompt) => void | Promise<void>;
  quickActions?: React.ReactNode;
  toolbarExtra?: React.ReactNode;
  input: string;
  onInputChange: (value: string) => void;
  onPressEnter?: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onSend: () => void;
  onStop: () => void;
  loading?: boolean;
  disabled?: boolean;
  stopDisabled?: boolean;
  sendDisabled?: boolean;
  placeholder?: string;
  sidePanel?: React.ReactNode;
}

function textOf(value: unknown): string {
  if (value === undefined || value === null) return '';
  return String(value);
}

function recordOf(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function parseRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value === 'string') {
    return recordOf(jsonParse(value, null));
  }
  return recordOf(value);
}

export function eventPayload(event: SkillFactoryCodingEvent): Record<string, unknown> | null {
  return recordOf(event.payload) || parseRecord(event.payloadJson);
}

function eventModelContentBlock(event: SkillFactoryCodingEvent): Record<string, unknown> | null {
  return (
    recordOf(event.modelContentBlock) ||
    parseRecord(event.modelContentBlockJson) ||
    recordOf(event.content?.modelContentBlock)
  );
}

function eventContent(event: SkillFactoryCodingEvent): Record<string, unknown> {
  return event.content || {};
}

function eventStructuredText(event: SkillFactoryCodingEvent): string {
  const block = eventModelContentBlock(event);
  const payload = eventPayload(event);
  const payloadContent = recordOf(payload?.content);
  const content = eventContent(event);
  return textOf(
    block?.text ||
      block?.content ||
      block?.delta ||
      payloadContent?.text ||
      payloadContent?.content ||
      payload?.text ||
      payload?.content ||
      content.text ||
      content.content ||
      content.summary ||
      content.errorMsg ||
      event.errorMsg ||
      event.title,
  );
}

function modelBlockType(event: SkillFactoryCodingEvent): string {
  return textOf(eventModelContentBlock(event)?.type);
}

function isModelContentType(event: SkillFactoryCodingEvent, blockType: string): boolean {
  return event.eventType === STREAM_MODEL_CONTENT_EVENT_TYPE && modelBlockType(event) === blockType;
}

function isThinkingEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    event.eventType === STREAM_THINKING_EVENT_TYPE ||
    isModelContentType(event, MODEL_CONTENT_TYPE_THINKING)
  );
}

function isTextDeltaEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    isModelContentType(event, MODEL_CONTENT_TYPE_TEXT) || event.eventType === 'ANSWER_TEXT_DELTA'
  );
}

function isToolEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    event.eventType === 'TOOL_CALL' ||
    event.eventType === 'TOOL_RESULT' ||
    event.eventType === STREAM_EVENT_TOOL_CALL_STARTED ||
    event.eventType === STREAM_EVENT_TOOL_CALL_FINISHED
  );
}

function isBusinessEvent(event: SkillFactoryCodingEvent): boolean {
  if (isDiagnosticErrorEvent(event)) return false;
  return (
    event.eventType === AUTHORING_EVENT_A2UI_MESSAGE ||
    event.eventType === AUTHORING_EVENT_BUSINESS_INTERACTION ||
    event.eventType === STREAM_EVENT_ARTIFACT_CREATED
  );
}

function isObservationEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    event.eventType === AUTHORING_EVENT_OBSERVATION ||
    event.eventType === AUTHORING_EVENT_OBSERVATION_CREATED
  );
}

function isCompletedEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    event.eventType === LEGACY_EVENT_COMPLETED || event.eventType === STREAM_EVENT_RUN_COMPLETED
  );
}

function isTerminalFailureEvent(event: SkillFactoryCodingEvent): boolean {
  return event.eventType === LEGACY_EVENT_FAILED || event.eventType === STREAM_EVENT_RUN_FAILED;
}

function isCancelledEvent(event: SkillFactoryCodingEvent): boolean {
  return event.eventType === STREAM_EVENT_RUN_CANCELLED;
}

function isDiagnosticErrorEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    event.eventType === DIAGNOSTIC_EVENT_ERROR ||
    (event.eventType !== LEGACY_EVENT_FAILED &&
      event.eventCode === LEGACY_EVENT_FAILED &&
      event.success === false)
  );
}

export function eventText(event: SkillFactoryCodingEvent): string {
  return eventStructuredText(event);
}

function eventMessageId(event: SkillFactoryCodingEvent): string {
  return (
    event.messageId || event.runId || event.sessionId || `msg_${event.timestamp || Date.now()}`
  );
}

function collapseWhitespace(value: string): string {
  return value?.replace(/\s+/g, ' ')?.trim?.() || '';
}

function trimTraceText(value: string, maxLength = TRACE_DETAIL_MAX_LENGTH): string {
  const text = collapseWhitespace(value);
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}

function formatJson(value: unknown): string {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value === 'string') return value;
  return jsonStringify(value, null, 2);
}

function displayValue(value: unknown): string {
  if (typeof value === 'string') return value;
  return formatJson(value) || textOf(value);
}

function isToolCallStartedEvent(event: SkillFactoryCodingEvent): boolean {
  return event.eventType === 'TOOL_CALL' || event.eventType === STREAM_EVENT_TOOL_CALL_STARTED;
}

function isToolCallFinishedEvent(event: SkillFactoryCodingEvent): boolean {
  return event.eventType === 'TOOL_RESULT' || event.eventType === STREAM_EVENT_TOOL_CALL_FINISHED;
}

function debugEventTitle(event: SkillFactoryCodingEvent): string {
  if (isThinkingEvent(event)) {
    return '思考过程';
  }
  if (isToolCallStartedEvent(event)) {
    return `调用工具 ${traceToolName(event) || '-'}`;
  }
  if (isToolCallFinishedEvent(event)) {
    return `工具结果 ${traceToolName(event) || '-'}`;
  }
  if (isObservationEvent(event)) {
    return '业务动作 Observation';
  }
  if (isTerminalFailureEvent(event)) {
    return '执行失败';
  }
  if (isCancelledEvent(event)) {
    return '运行已停止';
  }
  if (isDiagnosticErrorEvent(event)) {
    return '执行异常';
  }
  return event.eventType === 'STDERR' ? 'stderr' : textOf(event.title || event.eventType);
}

function debugEventBody(event: SkillFactoryCodingEvent): string {
  if (isThinkingEvent(event)) {
    return eventStructuredText(event);
  }
  if (isToolCallStartedEvent(event)) {
    return displayValue(traceToolArgs(event) || eventPayload(event) || eventContent(event));
  }
  if (isToolCallFinishedEvent(event)) {
    return displayValue(traceToolResult(event));
  }
  if (isObservationEvent(event)) {
    const content = eventContent(event);
    return textOf(event.observation?.summary || content.summary || content);
  }
  return eventStructuredText(event);
}

function recordFromValue(value: unknown): Record<string, unknown> | null {
  if (!value) return null;
  if (typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>;
  if (typeof value !== 'string') return null;
  const parsed = jsonParse(value, null);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
  return parsed as Record<string, unknown>;
}

function traceToolName(event: SkillFactoryCodingEvent): string {
  const payload = eventPayload(event);
  const content = eventContent(event);
  const block = eventModelContentBlock(event);
  return (
    textOf(
      event.toolName ||
        payload?.toolName ||
        payload?.toolCallName ||
        payload?.name ||
        content.toolName ||
        content.toolCallName ||
        content.name ||
        block?.toolName,
    ) || '工具'
  );
}

function traceToolCallId(event: SkillFactoryCodingEvent): string {
  const payload = eventPayload(event);
  const content = eventContent(event);
  const block = eventModelContentBlock(event);
  return textOf(event.toolCallId || payload?.toolCallId || content.toolCallId || block?.toolCallId);
}

function traceToolArgs(event: SkillFactoryCodingEvent): unknown {
  const payload = eventPayload(event);
  const content = eventContent(event);
  const block = eventModelContentBlock(event);
  return event.toolArgs || payload?.toolArgs || content.toolArgs || block?.toolArgs;
}

function traceToolResult(event: SkillFactoryCodingEvent): unknown {
  const payload = eventPayload(event);
  const content = eventContent(event);
  return (
    payload?.result ||
    payload?.output ||
    payload?.content ||
    content.result ||
    content.output ||
    content
  );
}

function traceToolSuccess(event: SkillFactoryCodingEvent): boolean | undefined {
  const payload = eventPayload(event);
  const content = eventContent(event);
  if (typeof event.toolSuccess === 'boolean') return event.toolSuccess;
  if (typeof payload?.toolSuccess === 'boolean') return payload.toolSuccess;
  if (typeof payload?.success === 'boolean') return payload.success;
  if (typeof content.toolSuccess === 'boolean') return content.toolSuccess;
  if (typeof event.success === 'boolean') return event.success;
  return undefined;
}

function traceToolArgsSummary(value: unknown): string {
  const record = recordFromValue(value);
  if (record) {
    const importantKeys = [
      'skillCode',
      'path',
      'filePath',
      'pattern',
      'query',
      'command',
      'maxDepth',
    ];
    const parts = importantKeys
      ?.filter((key) => record[key] !== undefined && record[key] !== null && record[key] !== '')
      ?.map?.((key) => `${key}=${trimTraceText(displayValue(record[key]), 72)}`);
    if (parts.length) return parts.join(', ');
  }
  return trimTraceText(displayValue(value));
}

function traceToolStageLabel(toolName: string): string {
  if (toolName === 'use_skill') {
    return '加载 Skill';
  }
  if (['diff', 'propose_patch', 'workspace_diff'].includes(toolName)) {
    return '处理文件变更';
  }
  if (toolName === 'python') {
    return '执行脚本';
  }
  return '调用工具';
}

function traceToolTitle(toolName: string): string {
  return toolName === 'use_skill' ? '加载 Skill' : `调用工具 ${toolName}`;
}

function traceToolFinishedDetail(event: SkillFactoryCodingEvent, toolName: string): string {
  if (toolName !== 'use_skill') {
    return trimTraceText(debugEventBody(event), TRACE_RAW_DETAIL_MAX_LENGTH);
  }
  const result = recordFromValue(traceToolResult(event));
  if (!result) return 'Skill 加载完成';
  const skillCode = textOf(result.skillCode) || 'Skill';
  const version = textOf(result.version);
  const fileCount = textOf(result.fileCount);
  return `已加载 ${skillCode}${version ? ` 正式版 ${version}` : ''}${
    fileCount ? `，共 ${fileCount} 个文件` : ''
  }`;
}

function traceStageTitle(stage: ExecutionTraceStage): string {
  if (stage.title) return stage.title;
  if (stage.status === 'error') return `${stage.label}失败`;
  if (stage.status === 'done') return `已${stage.label}`;
  return `正在${stage.label}`;
}

function traceStageStatusText(stage: ExecutionTraceStage): string {
  if (stage.status === 'error') return '异常';
  if (stage.status === 'done') return '完成';
  return '进行中';
}

function traceEventDetail(event: SkillFactoryCodingEvent): {
  key: string;
  label: string;
  title?: string;
  status: ExecutionTraceStageStatus;
  detail: string;
} {
  const content = event.content || {};
  if (event.eventType === STREAM_EVENT_TRANSPORT_RECOVERING) {
    return {
      key: 'transport-recovering',
      label: '恢复连接',
      title: '连接中断，正在恢复',
      status: 'running',
      detail: trimTraceText(debugEventBody(event) || '正在查询后端运行状态'),
    };
  }
  if (event.eventType === AUTHORING_EVENT_AG_UI) {
    const payload = eventPayload(event);
    const status = textOf(content.status || payload?.status);
    const stageStatus =
      status === 'error' || event.success === false
        ? 'error'
        : status === 'done'
        ? 'done'
        : 'running';
    const title = textOf(
      event.title || content.title || payload?.title || content.summary || '执行过程',
    );
    return {
      key:
        textOf(content.stageId || payload?.stageId) ||
        textOf(content.toolCallId || payload?.toolCallId) ||
        title ||
        AUTHORING_EVENT_AG_UI,
      label: title,
      title,
      status: stageStatus,
      detail: trimTraceText(
        textOf(content.summary || payload?.summary) ||
          textOf(content.toolName || payload?.toolName) ||
          textOf(content.type || payload?.type) ||
          debugEventBody(event),
      ),
    };
  }
  if (isToolCallStartedEvent(event)) {
    const toolName = traceToolName(event);
    const toolCallId = traceToolCallId(event);
    const argsSummary = traceToolArgsSummary(
      traceToolArgs(event) || eventPayload(event) || content,
    );
    const title = traceToolTitle(toolName);
    return {
      key: toolCallId ? `tool:${toolCallId}` : `tool-${traceToolStageLabel(toolName)}`,
      label: title,
      title,
      status: 'running',
      detail: `${title}${argsSummary ? `：${argsSummary}` : ''}`,
    };
  }
  if (isToolCallFinishedEvent(event)) {
    const toolName = traceToolName(event);
    const toolCallId = traceToolCallId(event);
    const hasError =
      traceToolSuccess(event) === false || Boolean(content.errorMsg || event.errorMsg);
    const title = traceToolTitle(toolName);
    return {
      key: toolCallId ? `tool:${toolCallId}` : `tool-${traceToolStageLabel(toolName)}`,
      label: title,
      title,
      status: hasError ? 'error' : 'done',
      detail: hasError
        ? `${title}失败：${trimTraceText(debugEventBody(event), TRACE_RAW_DETAIL_MAX_LENGTH)}`
        : traceToolFinishedDetail(event, toolName),
    };
  }
  if (event.eventType === 'STDOUT' || event.eventType === 'STDERR') {
    return {
      key: 'script-output',
      label: '查看输出',
      status: event.eventType === 'STDERR' ? 'error' : 'done',
      detail: `${event.eventType?.toLowerCase?.()}：${trimTraceText(debugEventBody(event))}`,
    };
  }
  if (isObservationEvent(event)) {
    return {
      key: 'authoring-observation',
      label: '记录业务确认',
      status: 'done',
      detail: trimTraceText(debugEventBody(event)),
    };
  }
  if (isCancelledEvent(event)) {
    return {
      key: 'cancelled',
      label: '停止运行',
      title: '运行已停止',
      status: 'done',
      detail: trimTraceText(debugEventBody(event) || '本轮运行已停止'),
    };
  }
  if (isTerminalFailureEvent(event)) {
    return {
      key: 'failed',
      label: '执行过程',
      status: 'error',
      detail: trimTraceText(debugEventBody(event) || '执行失败'),
    };
  }
  if (isDiagnosticErrorEvent(event)) {
    const toolCallId = traceToolCallId(event);
    const toolName = traceToolName(event);
    const title = traceToolTitle(toolName);
    return {
      key: toolCallId ? `tool:${toolCallId}` : 'diagnostic-error',
      label: toolCallId ? title : '执行过程',
      title: toolCallId ? title : undefined,
      status: 'error',
      detail: trimTraceText(debugEventBody(event) || '执行过程出现异常'),
    };
  }
  return {
    key: `event-${event.eventType}`,
    label: '处理执行事件',
    status: 'done',
    detail: trimTraceText(debugEventBody(event)),
  };
}

function patchEventKey(event: SkillFactoryCodingEvent, fallback: string | number): string {
  return event.patchId || `${event.sessionId || 'artifact'}-${fallback}`;
}

function codingEventIdentity(event: SkillFactoryCodingEvent): string {
  return (
    event.eventId ||
    event.recordId ||
    [
      event.sessionId,
      event.messageId,
      event.runId,
      event.eventType,
      event.eventCode,
      event.patchId,
      event.blockId,
      event.toolCallId,
      event.timestamp,
    ]
      ?.filter((value) => value !== undefined && value !== null && value !== '')
      ?.join?.(':')
  );
}

export function authoringChangeSetId(event: SkillFactoryCodingEvent): string {
  return codingEventIdentity(event);
}

function uniqueCodingEvents(events: SkillFactoryCodingEvent[]): SkillFactoryCodingEvent[] {
  return mergeCodingEvents([], events);
}

function isHighFrequencyModelDelta(event: SkillFactoryCodingEvent): boolean {
  return isTextDeltaEvent(event) || isThinkingEvent(event);
}

function streamingDeltaKey(event: SkillFactoryCodingEvent): string {
  return [
    event.sessionId,
    eventMessageId(event),
    event.blockId || 'default',
    event.eventType,
    modelBlockType(event),
  ].join(':');
}

function mergeStreamingDelta(
  previous: SkillFactoryCodingEvent,
  next: SkillFactoryCodingEvent,
): SkillFactoryCodingEvent {
  const text = `${eventText(previous)}${eventText(next)}`;
  const previousBlock = eventModelContentBlock(previous);
  const nextBlock = eventModelContentBlock(next);
  const modelContentBlock =
    previousBlock || nextBlock
      ? {
          ...(previousBlock || {}),
          ...(nextBlock || {}),
          text,
        }
      : undefined;
  return {
    ...previous,
    ...next,
    recordId: previous.recordId || next.recordId,
    eventId: previous.eventId || next.eventId,
    timestamp: previous.timestamp || next.timestamp,
    content: {
      ...(previous.content || {}),
      ...(next.content || {}),
      text,
    },
    modelContentBlock,
  };
}

function mergeCodingEvents(
  current: SkillFactoryCodingEvent[],
  additions: SkillFactoryCodingEvent[],
): SkillFactoryCodingEvent[] {
  const positions = new Map<string, number>();
  const streamPositions = new Map<string, number>();
  const result: SkillFactoryCodingEvent[] = [];
  [...current, ...additions].forEach((event) => {
    if (isHighFrequencyModelDelta(event)) {
      const streamKey = streamingDeltaKey(event);
      const streamPosition = streamPositions.get(streamKey);
      if (streamPosition !== undefined) {
        result[streamPosition] = mergeStreamingDelta(result[streamPosition], event);
        return;
      }
      streamPositions.set(streamKey, result.length);
    }
    const identity = codingEventIdentity(event);
    const position = identity ? positions.get(identity) : undefined;
    if (position === undefined) {
      if (identity) positions.set(identity, result.length);
      result.push(event);
      return;
    }
    result[position] = { ...result[position], ...event };
  });
  return result;
}

function mergePatchEvent(
  previous: SkillFactoryCodingEvent,
  next: SkillFactoryCodingEvent,
): SkillFactoryCodingEvent {
  return {
    ...previous,
    ...next,
    title: next.title || previous.title,
    content: {
      ...(previous.content || {}),
      ...(next.content || {}),
    },

    observation: next.observation || previous.observation,
  };
}

function isExecutionTraceEvent(event: SkillFactoryCodingEvent): boolean {
  return (
    isThinkingEvent(event) ||
    isToolEvent(event) ||
    event.eventType === 'STDOUT' ||
    event.eventType === 'STDERR' ||
    event.eventType === AUTHORING_EVENT_AG_UI ||
    isPatchEvent(event) ||
    isObservationEvent(event) ||
    isTerminalFailureEvent(event) ||
    isCancelledEvent(event) ||
    isDiagnosticErrorEvent(event)
  );
}

export function buildExecutionTraceBlocks(
  events: SkillFactoryCodingEvent[],
  pendingFinalAnswer = false,
  pendingTimestamp?: number,
): ExecutionTraceRenderBlock[] {
  const blocks: ExecutionTraceRenderBlock[] = [];
  let progressBlock: ExecutionTraceRenderBlock | null = null;
  const stageMap = new Map<string, ExecutionTraceStage>();
  const artifactBlockMap = new Map<string, ExecutionTraceRenderBlock>();
  const customResultIds = domainResultToolCallIds(events);
  let thinkingStageIndex = 0;
  let activeThinkingStageKey = '';

  const ensureProgressBlock = (timestamp?: number): ExecutionTraceRenderBlock => {
    if (progressBlock) return progressBlock;
    progressBlock = {
      key: 'progress',
      type: 'progress',
      status: 'running',
      text: '',
      stages: [],
      timestamp,
    };
    blocks.push(progressBlock);
    return progressBlock;
  };

  const closeRunningStagesExcept = (activeKey: string) => {
    stageMap.forEach((stage, key) => {
      if (key !== activeKey && stage.status === 'running') {
        stage.status = 'done';
      }
    });
  };

  const ensureStage = (
    key: string,
    label: string,
    status: ExecutionTraceStageStatus,
    timestamp?: number,
    title?: string,
  ): ExecutionTraceStage => {
    if (status === 'running') {
      closeRunningStagesExcept(key);
    }
    const existed = stageMap.get(key);
    if (existed) {
      existed.status = status === 'error' ? 'error' : status;
      existed.label = label || existed.label;
      existed.title = title || existed.title;
      existed.timestamp = timestamp || existed.timestamp;
      return existed;
    }
    const stage: ExecutionTraceStage = {
      key,
      label,
      title,
      status,
      details: [],
      events: [],
      timestamp,
    };
    stageMap.set(key, stage);
    return stage;
  };

  const closeActiveThinkingStage = () => {
    if (!activeThinkingStageKey) return;
    const stage = stageMap.get(activeThinkingStageKey);
    if (stage?.status === 'running') {
      stage.status = 'done';
    }
    activeThinkingStageKey = '';
  };

  const closePatchActionStage = (event: SkillFactoryCodingEvent) => {
    const settledCode = textOf(event.eventCode || event.eventType);
    const toolName = settledCode === 'PATCH_DISCARDED' ? 'discard_patch' : 'confirm_patch';
    stageMap.forEach((stage) => {
      if (stage.status !== 'running') return;
      const matched = stage.events?.some?.((stageEvent) => traceToolName(stageEvent) === toolName);
      if (!matched) return;
      stage.status = 'done';
      stage.details = [
        ...stage.details,
        settledCode === 'PATCH_DISCARDED' ? 'patch 已丢弃。' : 'patch 已应用。',
      ];
      stage.events?.push?.(event);
    });
  };

  events.forEach((event, index) => {
    if (isThinkingEvent(event)) {
      const block = ensureProgressBlock(event.timestamp);
      const thinkingDelta = debugEventBody(event);
      block.text = `${block.text || ''}${thinkingDelta}`;
      if (thinkingDelta) {
        activeThinkingStageKey = event.blockId
          ? `thinking:${event.blockId}`
          : activeThinkingStageKey || `thinking-${thinkingStageIndex++}`;
        const stage = ensureStage(
          activeThinkingStageKey,
          '思考您的请求',
          'running',
          event.timestamp,
        );
        stage.rawDetail = `${stage.rawDetail || ''}${thinkingDelta}`;
        const detailText = trimTraceText(stage.rawDetail, TRACE_RAW_DETAIL_MAX_LENGTH);
        stage.details = detailText ? [detailText] : [];
        stage.events?.push?.(event);
      }
      block.timestamp = event.timestamp || block.timestamp;
      return;
    }
    closeActiveThinkingStage();
    if (isPatchEvent(event)) {
      if (isPatchSettledEvent(event)) {
        closePatchActionStage(event);
      }
      const key = `artifact-${patchEventKey(event, event.timestamp || index)}`;
      const existed = artifactBlockMap.get(key);
      if (existed) {
        existed.event = existed.event ? mergePatchEvent(existed.event, event) : event;
        existed.timestamp = event.timestamp || existed.timestamp;
      } else {
        const block: ExecutionTraceRenderBlock = {
          key,
          type: 'artifact',
          event,
          timestamp: event.timestamp,
        };
        artifactBlockMap.set(key, block);
        blocks.push(block);
      }
      return;
    }
    const detail = traceEventDetail(event);
    const block = ensureProgressBlock(event.timestamp);
    const stage = ensureStage(
      detail.key,
      detail.label,
      detail.status,
      event.timestamp,
      detail.title,
    );
    if (detail.detail && shouldDisplayGenericToolResult(event, customResultIds)) {
      stage.details?.push?.(detail.detail);
    }
    stage.events?.push?.(event);
    block.timestamp = event.timestamp || block.timestamp;
  });

  if (pendingFinalAnswer && !progressBlock) {
    ensureProgressBlock(pendingTimestamp);
  }
  const finalProgressBlock = progressBlock as ExecutionTraceRenderBlock | null;
  if (finalProgressBlock) {
    let stages = Array.from(stageMap.values());
    const hasTerminalError = stages.some(
      (stage) =>
        stage.status === 'error' &&
        (stage.key === 'failed' ||
          stage.events?.some?.((stageEvent) => isTerminalFailureEvent(stageEvent)) ||
          stage.events?.some?.((stageEvent) => stageEvent.eventType === 'STDERR')),
    );
    if (hasTerminalError) {
      finalProgressBlock.status = 'error';
    } else if (pendingFinalAnswer) {
      if (!stages.some((stage) => stage.status === 'running')) {
        ensureStage(
          'waiting-final-answer',
          '思考您的请求',
          'running',
          pendingTimestamp || finalProgressBlock.timestamp,
        );
        stages = Array.from(stageMap.values());
      }
      finalProgressBlock.status = 'running';
    } else {
      stages.forEach((stage) => {
        if (stage.status === 'running') {
          stage.status = 'done';
        }
      });
      finalProgressBlock.status = 'done';
    }
    finalProgressBlock.stages = stages;
  }

  return blocks;
}

export function buildAuthoringMessages(
  events: SkillFactoryCodingEvent[],
  isBusinessEventVisible?: (event: SkillFactoryCodingEvent) => boolean,
): SkillFactoryAuthoringMessage[] {
  const messageMap = new Map<string, SkillFactoryAuthoringMessage>();
  const ensureMessage = (event: SkillFactoryCodingEvent): SkillFactoryAuthoringMessage => {
    const messageId = eventMessageId(event);
    const existed = messageMap.get(messageId);
    if (existed) return existed;
    const nextMessage: SkillFactoryAuthoringMessage = {
      messageId,
      sessionId: event.sessionId,
      runId: event.runId,
      timestamp: event.timestamp || Date.now(),
      status: 'streaming',
      answerText: '',
      events: [],
      executionTrace: [],
      businessEvents: [],
    };
    messageMap.set(messageId, nextMessage);
    return nextMessage;
  };

  events.forEach((event) => {
    const messageState = ensureMessage(event);
    messageState.timestamp = Math.min(
      messageState.timestamp,
      event.timestamp || messageState.timestamp,
    );
    messageState.events?.push?.(event);
    if (isTextDeltaEvent(event)) {
      messageState.answerText += eventText(event);
    }
    if (isBusinessEvent(event) && (isBusinessEventVisible?.(event) ?? true)) {
      messageState.businessEvents?.push?.(event);
    }
    if (isExecutionTraceEvent(event)) {
      messageState.executionTrace?.push?.(event);
    }
    if (isCancelledEvent(event)) {
      messageState.status = 'cancelled';
    } else if (isTerminalFailureEvent(event)) {
      messageState.status = 'error';
    } else if (isCompletedEvent(event)) {
      messageState.status = 'done';
    }
  });
  return Array.from(messageMap.values()).sort((a, b) => a.timestamp - b.timestamp);
}

export function useSkillFactoryChatStream<TDraft = unknown>({
  adapter,
  transport = skillFactorySseTransport,
  workspaceId = 'component-center',
  currentDraft,
}: UseSkillFactoryChatStreamOptions<TDraft>): UseSkillFactoryChatStreamResult {
  const [input, setInput] = useState('');
  const [eventStore, setEventStore] = useState<{
    events: SkillFactoryCodingEvent[];
    renderRevision: number;
  }>({ events: [], renderRevision: 0 });
  const { events, renderRevision } = eventStore;
  const [turns, setTurns] = useState<SkillFactoryChatTurn[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState('');
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [sessionOptions, setSessionOptions] = useState<AuthoringSessionSummary[]>([]);
  const [authoringGuideConfig, setAuthoringGuideConfig] = useState<AuthoringGuideConfig>();
  const [historyLoading, setHistoryLoading] = useState(false);
  const [activeRunStatus, setActiveRunStatus] = useState<SkillFactoryRunStatus | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const recoveryAbortControllerRef = useRef<AbortController | null>(null);
  const latestSessionIdRef = useRef('');
  const historyRequestIdRef = useRef(0);
  const runStatusRequestIdRef = useRef(0);
  const pendingTurnsRef = useRef<SkillFactoryChatTurn[]>([]);
  const locallySettledInvokeIdsRef = useRef<Set<string>>(new Set());
  const pendingStreamEventsRef = useRef<SkillFactoryCodingEvent[]>([]);
  const streamFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sessionDisabledReason = MANAGEMENT_AI_PAUSE_REASON;
  const chatRunning = loading || isActiveCodingRun(activeRunStatus);

  const takePendingStreamEvents = () => {
    if (streamFlushTimerRef.current) {
      clearTimeout(streamFlushTimerRef.current);
      streamFlushTimerRef.current = null;
    }
    const pendingEvents = pendingStreamEventsRef.current;
    pendingStreamEventsRef.current = [];
    return pendingEvents;
  };

  const discardPendingStreamEvents = () => {
    takePendingStreamEvents();
  };

  const replaceEvents = (nextEvents: SkillFactoryCodingEvent[]) => {
    discardPendingStreamEvents();
    setEventStore((current) => ({
      events: uniqueCodingEvents(nextEvents),
      renderRevision: current.renderRevision + 1,
    }));
  };

  const flushStreamEvents = (immediateEvent?: SkillFactoryCodingEvent) => {
    const additions = takePendingStreamEvents();
    if (immediateEvent) {
      additions.push(immediateEvent);
    }
    if (!additions.length) return;
    setEventStore((current) => ({
      events: mergeCodingEvents(current.events, additions),
      renderRevision: current.renderRevision + 1,
    }));
  };

  const enqueueStreamEvent = (event: SkillFactoryCodingEvent) => {
    pendingStreamEventsRef.current = mergeCodingEvents(pendingStreamEventsRef.current, [event]);
    if (streamFlushTimerRef.current) return;
    streamFlushTimerRef.current = setTimeout(() => {
      flushStreamEvents();
    }, STREAM_RENDER_BATCH_MS);
  };

  useEffect(
    () => () => {
      if (streamFlushTimerRef.current) {
        clearTimeout(streamFlushTimerRef.current);
      }
      recoveryAbortControllerRef.current?.abort();
    },
    [],
  );

  const restoreRunStatus = async (historyEvents: SkillFactoryCodingEvent[], sessionId: string) => {
    const requestId = runStatusRequestIdRef.current + 1;
    runStatusRequestIdRef.current = requestId;
    const identity = latestUnfinishedCodingRun(historyEvents, sessionId);
    if (!identity) {
      setActiveRunStatus(null);
      return;
    }
    if (locallySettledInvokeIdsRef.current?.has?.(identity.invokeId)) {
      setActiveRunStatus(null);
      return;
    }
    try {
      const status = await skillFactoryApi.codingRunStatus(identity.sessionId, identity.invokeId);
      if (
        requestId === runStatusRequestIdRef.current &&
        !locallySettledInvokeIdsRef.current.has(identity.invokeId)
      ) {
        setActiveRunStatus(isActiveCodingRun(status) ? status : null);
      }
    } catch (error) {
      if (requestId === runStatusRequestIdRef.current) {
        setActiveRunStatus(null);
        message.error(error instanceof Error ? error.message : '运行状态查询失败');
      }
    }
  };

  const applyHistory = (history: AuthoringSessionHistory, options: HistoryApplyOptions = {}) => {
    const { replaceMessages = true } = options;
    const nextSessionId = history.selectedSessionId || history.activeSessionId || '';
    latestSessionIdRef.current = nextSessionId;
    setSelectedSessionId(nextSessionId);
    setActiveSessionId(history.activeSessionId || nextSessionId);
    setSessionOptions(history.sessions || []);
    setAuthoringGuideConfig(history.authoringGuideConfig);
    void restoreRunStatus(history.events || [], nextSessionId);
    if (!replaceMessages) {
      const persistedTurns = history.turns || [];
      const persistedTurnIds = new Set(persistedTurns.map((turn) => turn.id));
      pendingTurnsRef.current = pendingTurnsRef.current?.filter?.(
        (turn) => !persistedTurnIds.has(turn.id),
      );
      setTurns((current) => reconcilePersistedTurnAttribution(current, persistedTurns));
      return;
    }
    const historyTurns = (history.turns || []).map((turn: AuthoringChatTurn) => ({
      id: turn.id,
      role: turn.role,
      text: turn.text,
      timestamp: turn.timestamp,
      sessionId: turn.sessionId,
      messageId: turn.messageId,
      operator: turn.operator,
      optimistic: false,
    }));
    const persistedTurnIds = new Set(historyTurns.map((turn) => turn.id));
    pendingTurnsRef.current = pendingTurnsRef.current?.filter?.(
      (turn) => !persistedTurnIds.has(turn.id),
    );
    const mergedTurns = new Map<string, SkillFactoryChatTurn>();
    [...pendingTurnsRef.current, ...historyTurns].forEach((turn) => {
      mergedTurns.set(turn.id, turn);
    });
    setTurns(
      Array.from(mergedTurns.values()).sort((left, right) => left.timestamp - right.timestamp),
    );
    replaceEvents(history.events || []);
  };

  const reloadHistory = async (sessionId?: string, options: HistoryReloadOptions = {}) => {
    const { clearBeforeLoad = true, replaceMessages = true } = options;
    const requestId = historyRequestIdRef.current + 1;
    historyRequestIdRef.current = requestId;
    const targetSessionId = sessionId !== undefined ? sessionId : selectedSessionId;
    if (sessionDisabledReason || !adapter.sessionScope?.bizKey || !adapter.sessionScope?.scopeId) {
      setSessionOptions([]);
      setAuthoringGuideConfig(undefined);
      setSelectedSessionId('');
      setActiveSessionId('');
      setTurns([]);
      replaceEvents([]);
      pendingTurnsRef.current = [];
      setActiveRunStatus(null);
      runStatusRequestIdRef.current += 1;
      setHistoryLoading(false);
      return;
    }
    if (sessionId !== undefined && clearBeforeLoad) {
      latestSessionIdRef.current = sessionId;
      setSelectedSessionId(sessionId);
      setTurns([]);
      replaceEvents([]);
      pendingTurnsRef.current = [];
    }
    setHistoryLoading(true);
    try {
      const history = await skillFactoryApi.authoringSessionHistory({
        ...adapter.sessionScope,
        sessionId: targetSessionId || undefined,
      });
      if (requestId !== historyRequestIdRef.current) {
        return;
      }
      applyHistory(history, { replaceMessages });
    } catch (error) {
      if (requestId === historyRequestIdRef.current) {
        message.error(error instanceof Error ? error.message : '会话历史加载失败');
      }
    } finally {
      if (requestId === historyRequestIdRef.current) {
        setHistoryLoading(false);
      }
    }
  };

  const refreshSessionMetadata = async (sessionId?: string) => {
    await reloadHistory(sessionId, { clearBeforeLoad: false, replaceMessages: false });
  };

  useEffect(() => {
    recoveryAbortControllerRef.current?.abort();
    recoveryAbortControllerRef.current = null;
    pendingTurnsRef.current = [];
    locallySettledInvokeIdsRef.current?.clear?.();
    reloadHistory('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    adapter.sessionScope?.bizKey,
    adapter.sessionScope?.scopeType,
    adapter.sessionScope?.scopeId,
    adapter.sessionScope?.workspaceId,
    sessionDisabledReason,
  ]);

  const appendEvent = (event: SkillFactoryCodingEvent) => {
    if (event.sessionId) {
      latestSessionIdRef.current = event.sessionId;
      setSelectedSessionId((current) => current || event.sessionId);
      setActiveSessionId(event.sessionId);
      setTurns((prev) =>
        prev.some((turn) => turn.sessionId === 'pending')
          ? prev.map((turn) =>
              turn.sessionId === 'pending' ? { ...turn, sessionId: event.sessionId } : turn,
            )
          : prev,
      );
      if (pendingTurnsRef.current?.some?.((turn) => turn.sessionId === 'pending')) {
        pendingTurnsRef.current = pendingTurnsRef.current?.map?.((turn) =>
          turn.sessionId === 'pending' ? { ...turn, sessionId: event.sessionId } : turn,
        );
      }
    }
    const invokeId = event.invokeId || event.messageId || event.runId || '';
    const eventSessionId = event.sessionId || latestSessionIdRef.current;
    if (invokeId && eventSessionId) {
      if (isTerminalCodingRunEvent(event.eventType)) {
        runStatusRequestIdRef.current += 1;
        locallySettledInvokeIdsRef.current?.add?.(invokeId);
        setActiveRunStatus((current) => (current?.invokeId === invokeId ? null : current));
      } else if (!locallySettledInvokeIdsRef.current?.has?.(invokeId)) {
        setActiveRunStatus((current) =>
          current?.sessionId === eventSessionId &&
          current.invokeId === invokeId &&
          current.status === 'RUNNING'
            ? current
            : {
                sessionId: eventSessionId,
                invokeId,
                status: 'RUNNING',
                updateTime: event.timestamp || Date.now(),
              },
        );
      }
    }
    if (isHighFrequencyModelDelta(event)) {
      enqueueStreamEvent(event);
    } else {
      flushStreamEvents(event);
    }
    adapter.onEvent?.(event);
  };

  const selectSession = async (sessionId: string) => {
    await reloadHistory(sessionId);
  };

  const send = async (messageText?: string, options: AuthoringSendOptions = {}) => {
    const text = (messageText ?? input).trim();
    if (!text || chatRunning || historyLoading || sessionDisabledReason) return;
    if (text === '/new') {
      const requestId = historyRequestIdRef.current + 1;
      historyRequestIdRef.current = requestId;
      setInput('');
      setHistoryLoading(true);
      pendingTurnsRef.current = [];
      try {
        const created = await skillFactoryApi.authoringSessionCreate(adapter.sessionScope);
        if (requestId !== historyRequestIdRef.current) {
          return;
        }
        const nextSessionId = created.sessionId;
        if (!nextSessionId) {
          throw new Error('新建会话未返回 sessionId');
        }
        latestSessionIdRef.current = nextSessionId;
        setSelectedSessionId(nextSessionId);
        setActiveSessionId(nextSessionId);
        setTurns([]);
        replaceEvents([]);
        const history = await skillFactoryApi.authoringSessionHistory({
          ...adapter.sessionScope,
          sessionId: nextSessionId,
        });
        if (requestId !== historyRequestIdRef.current) {
          return;
        }
        applyHistory(history);
        message.success('已创建新的会话');
      } catch (error) {
        message.error(error instanceof Error ? error.message : '新建会话失败');
      } finally {
        setHistoryLoading(false);
      }
      return;
    }
    const sessionId = latestSessionIdRef.current || selectedSessionId || activeSessionId || '';
    const turnId = `authoring_${Date.now()}`;
    const messageId = `msg_${turnId}`;
    const runId = `run_${turnId}`;
    const request = adapter.buildRequest({
      message: text,
      sessionId,
      messageId,
      runId,
      currentDraft,
    });
    const controller = new AbortController();
    recoveryAbortControllerRef.current?.abort();
    recoveryAbortControllerRef.current = null;
    abortControllerRef.current = controller;
    historyRequestIdRef.current += 1;
    runStatusRequestIdRef.current += 1;
    locallySettledInvokeIdsRef.current?.delete?.(messageId);
    setActiveRunStatus({
      sessionId,
      invokeId: messageId,
      status: 'RUNNING',
      updateTime: Date.now(),
    });
    setInput('');
    if (sessionId) {
      setActiveSessionId(sessionId);
      setSelectedSessionId(sessionId);
      latestSessionIdRef.current = sessionId;
    }
    const optimisticTurn: SkillFactoryChatTurn = {
      id: `user-${messageId}`,
      role: 'user',
      text: options.displayText?.trim() || text,
      timestamp: Date.now(),
      sessionId: sessionId || 'pending',
      messageId,
      optimistic: true,
    };
    pendingTurnsRef.current = [...pendingTurnsRef.current, optimisticTurn];
    setTurns((prev) => [
      ...prev.filter((turn) => !textOf(turn.id)?.startsWith?.(GUIDE_TURN_ID_PREFIX)),
      optimisticTurn,
    ]);
    setLoading(true);
    let terminalObserved = false;
    let transportErrorMessage = '';
    try {
      await transport(
        {
          ...request,
          ...(options.requestOverrides || {}),
          sessionId,
          conversationId: sessionId,
          messageId,
          runId,
          workspaceId: adapter.sessionScope?.workspaceId || workspaceId,
        },
        (event) => {
          const eventInvokeId = event.invokeId || event.messageId || event.runId || '';
          if (
            isTerminalCodingRunEvent(event.eventType) &&
            (!eventInvokeId || eventInvokeId === messageId)
          ) {
            terminalObserved = true;
          }
          appendEvent(event);
        },
        { signal: controller.signal },
      );
    } catch (error) {
      if ((error as Error)?.name === 'AbortError') return;
      transportErrorMessage = error instanceof Error ? error.message : 'AI 创建请求失败';
      message.error(`${transportErrorMessage}，正在恢复运行状态`);
    } finally {
      flushStreamEvents();
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      setLoading(false);
      const latestSessionId = latestSessionIdRef.current || sessionId;
      if (!latestSessionId || controller.signal?.aborted) return;
      if (terminalObserved) {
        await refreshSessionMetadata(latestSessionId);
        return;
      }
      appendEvent({
        eventType: STREAM_EVENT_TRANSPORT_RECOVERING,
        sessionId: latestSessionId,
        workspaceId: adapter.sessionScope?.workspaceId || workspaceId,
        messageId,
        invokeId: messageId,
        runId,
        title: '连接中断，正在恢复',
        content: {
          summary: transportErrorMessage || '流式连接已结束，正在查询后端运行状态',
        },
        timestamp: Date.now(),
      });
      const recoveryController = new AbortController();
      recoveryAbortControllerRef.current = recoveryController;
      try {
        const outcome = await recoverCodingRunAfterTransportEof<SkillFactoryRunStatus>({
          signal: recoveryController.signal,
          queryStatus: () => skillFactoryApi.codingRunStatus(latestSessionId, messageId),
          onStatus: (status) => {
            if (isActiveCodingRun(status)) {
              setActiveRunStatus(status);
            }
          },
        });
        if (outcome.kind === 'terminal') {
          locallySettledInvokeIdsRef.current?.add?.(messageId);
          setActiveRunStatus((current) => (current?.invokeId === messageId ? null : current));
          await reloadHistory(latestSessionId, { clearBeforeLoad: false });
        }
      } catch (error) {
        if (!recoveryController.signal?.aborted) {
          message.error(error instanceof Error ? error.message : '运行状态恢复失败');
        }
      } finally {
        if (recoveryAbortControllerRef.current === recoveryController) {
          recoveryAbortControllerRef.current = null;
        }
      }
    }
  };

  const runGuidePrompt = async (prompt: AuthoringGuidePrompt) => {
    const text = textOf(prompt.sendMsg || prompt.text)?.trim?.();
    if (!text) return;
    const actionType = textOf(prompt.actionType || GUIDE_ACTION_SEND)?.toUpperCase?.();
    if (actionType === GUIDE_ACTION_FILL_INPUT) {
      setInput((prev) => (prev.trim() ? `${prev.trim()}\n\n${text}` : text));
      return;
    }
    await send(text);
  };

  const stop = async () => {
    const runStatus = activeRunStatus;
    let cancelAccepted = false;
    let terminalObserved = false;
    recoveryAbortControllerRef.current?.abort();
    recoveryAbortControllerRef.current = null;
    runStatusRequestIdRef.current += 1;
    if (!runStatus?.sessionId || !runStatus.invokeId) {
      abortControllerRef.current?.abort?.();
      abortControllerRef.current = null;
      flushStreamEvents();
      setLoading(false);
      if (runStatus?.invokeId) {
        locallySettledInvokeIdsRef.current?.add?.(runStatus.invokeId);
      }
      setActiveRunStatus(null);
      return;
    }
    setActiveRunStatus({
      ...runStatus,
      status: 'CANCELLING',
      updateTime: Date.now(),
    });
    try {
      const cancellingStatus = await skillFactoryApi.codingRunCancel(
        runStatus.sessionId,
        runStatus.invokeId,
      );
      cancelAccepted = true;
      abortControllerRef.current?.abort?.();
      abortControllerRef.current = null;
      setLoading(false);
      const status = isActiveCodingRun(cancellingStatus)
        ? await skillFactoryApi.waitCodingRunTerminal(runStatus.sessionId, runStatus.invokeId)
        : cancellingStatus;
      if (isActiveCodingRun(status)) {
        setActiveRunStatus(status);
        message.success('已请求停止本轮 AI 运行');
      } else {
        terminalObserved = true;
        locallySettledInvokeIdsRef.current?.add?.(runStatus.invokeId);
        setActiveRunStatus(null);
        if (status.status === 'CANCELLED') {
          message.success('本轮 AI 运行已停止');
        } else if (status.status === 'COMPLETED') {
          message.success('本轮 AI 运行已完成');
        } else {
          message.error('本轮 AI 运行已失败');
        }
      }
    } catch (error) {
      setActiveRunStatus(
        cancelAccepted ? { ...runStatus, status: 'CANCELLING', updateTime: Date.now() } : runStatus,
      );
      message.error(
        cancelAccepted
          ? '停止请求已提交，但运行状态查询失败'
          : error instanceof Error
          ? error.message
          : '停止 AI 运行失败',
      );
    } finally {
      if (terminalObserved) {
        await reloadHistory(runStatus.sessionId, { clearBeforeLoad: false });
      } else {
        await refreshSessionMetadata(runStatus.sessionId);
      }
    }
  };

  const currentSessionId = selectedSessionId || activeSessionId;
  const visibleTurns = useMemo(
    () =>
      currentSessionId
        ? turns.filter(
            (turn) =>
              !turn.sessionId ||
              turn.sessionId === 'pending' ||
              turn.sessionId === currentSessionId,
          )
        : turns,
    [turns, currentSessionId],
  );
  const visibleEvents = useMemo(
    () =>
      currentSessionId
        ? events.filter((event) => !event.sessionId || event.sessionId === currentSessionId)
        : events,
    [events, currentSessionId],
  );

  const messages = useMemo(() => {
    const assistantTurns = new Map(
      visibleTurns
        ?.filter((turn) => turn.role === 'assistant' && turn.messageId)
        ?.map?.((turn) => [turn.messageId as string, turn]),
    );
    return buildAuthoringMessages(visibleEvents, adapter.isBusinessEventVisible)?.map?.((item) => {
      const persistedAnswer = assistantTurns.get(item.messageId);
      if (!persistedAnswer || item.answerText) return item;
      return {
        ...item,
        answerText: persistedAnswer.text,
        timestamp: Math.min(item.timestamp, persistedAnswer.timestamp),
      };
    });
  }, [visibleEvents, visibleTurns, adapter.isBusinessEventVisible]);
  const chatItems = useMemo<SkillFactoryAuthoringChatItem[]>(() => {
    const assistantMessageIds = new Set(messages.map((item) => item.messageId));
    return [
      ...visibleTurns
        ?.filter(
          (turn) =>
            turn.role !== 'assistant' ||
            !turn.messageId ||
            !assistantMessageIds.has(turn.messageId),
        )
        ?.map?.((turn) => ({ type: 'turn' as const, turn })),
      ...messages.map((assistantMessage) => ({
        type: 'assistant' as const,
        message: assistantMessage,
      })),
    ].sort((a, b) => {
      const left = a.type === 'turn' ? a.turn?.timestamp : a.message?.timestamp;
      const right = b.type === 'turn' ? b.turn?.timestamp : b.message?.timestamp;
      return left - right;
    });
  }, [visibleTurns, messages]);

  return {
    input,
    setInput,
    events,
    turns,
    messages,
    chatItems,
    renderRevision,
    loading: chatRunning,
    activeSessionId,
    selectedSessionId,
    sessionOptions,
    authoringGuideConfig,
    historyLoading,
    sessionDisabledReason,
    selectSession,
    reloadHistory,
    refreshSessionMetadata,
    send,
    runGuidePrompt,
    stop,
    appendEvent,
  };
}

function formatTime(timestamp?: number): string {
  if (!timestamp) return '-';
  return new Date(timestamp).toLocaleString('zh-CN', { hour12: false });
}

export function prepareMarkdownForRender(text: string, status: AssistantMessageStatus): string {
  return status === 'streaming' ? remend(text) : text;
}

export const MarkdownAnswer: React.FC<{
  text: string;
  status: AssistantMessageStatus;
}> = React.memo(({ text, status }) => {
  const renderedText = useMemo(() => prepareMarkdownForRender(text, status), [status, text]);
  return (
    <div className="skill-factory-chat-bubble markdown">
      <ReactMarkdown className="skill-factory-markdown-answer" remarkPlugins={[remarkGfm]}>
        {renderedText}
      </ReactMarkdown>
    </div>
  );
});

export const AnswerLayer: React.FC<{
  text: string;
  status: AssistantMessageStatus;
}> = React.memo(({ text, status }) => {
  if (text) {
    return (
      <div className="skill-factory-message-layer answer">
        <MarkdownAnswer text={text} status={status} />
      </div>
    );
  }
  return null;
});

function renderTraceStage(stage: ExecutionTraceStage, expanded: boolean) {
  const stageDetails = stage.details || [];
  const stageEvents = stage.events || [];
  return (
    <div className={`skill-factory-trace-stage ${stage.status}`} key={stage.key}>
      <span className="skill-factory-trace-stage-dot">
        {stage.status === 'done' ? <CheckOutlined /> : null}
        {stage.status === 'running' ? <span className="skill-factory-trace-stage-spinner" /> : null}
        {stage.status === 'error' ? <StopOutlined /> : null}
      </span>
      <div className="skill-factory-trace-stage-main">
        <div className="skill-factory-trace-stage-title">
          <strong>{traceStageTitle(stage)}</strong>
          <Tag
            color={
              stage.status === 'error' ? 'error' : stage.status === 'done' ? 'blue' : 'warning'
            }
          >
            {traceStageStatusText(stage)}
          </Tag>
        </div>
        {stageDetails.length ? (
          <div className="skill-factory-trace-stage-details">
            {stageDetails.map((detail, index) => (
              <p key={`${stage.key}-detail-${index}`}>{detail}</p>
            ))}
          </div>
        ) : null}
        {expanded && stageEvents.length ? (
          <details className="skill-factory-trace-raw">
            <summary>查看原始事件</summary>
            <pre>
              {stageEvents
                ?.map(
                  (event) =>
                    `${event.eventType} · ${debugEventTitle(event)}\n${debugEventBody(event)}`,
                )
                ?.join?.('\n\n')}
            </pre>
          </details>
        ) : null}
      </div>
    </div>
  );
}

function artifactSummary(event: SkillFactoryCodingEvent): string {
  const content = eventContent(event);
  const payload = eventPayload(event);
  const changedFilesFromPayload = Array.isArray(payload?.changedFiles) ? payload?.changedFiles : [];
  const changedFiles = Array.isArray(content.changedFiles)
    ? content.changedFiles
    : changedFilesFromPayload;
  if (isPatchEvent(event)) {
    return changedFiles.length ? `文件变更 ${changedFiles.length} 个` : '文件变更草稿已生成';
  }
  return trimTraceText(eventText(event) || formatJson(eventPayload(event) || content));
}

function renderArtifactBlock(block: ExecutionTraceRenderBlock) {
  const event = block.event;
  if (!event) return null;
  return (
    <div className="skill-factory-debug-block final compact" key={block.key}>
      <div className="skill-factory-debug-block-head">
        <Space>
          <Tag color="warning">{event.payloadType || event.eventCode || 'ARTIFACT'}</Tag>
          <strong>{event.title || '运行产物'}</strong>
        </Space>
        <Text type="secondary">{formatTime(event.timestamp)}</Text>
      </div>
      <div className="skill-factory-debug-block-body">{artifactSummary(event)}</div>
      <details className="skill-factory-trace-raw">
        <summary>查看结构化数据</summary>
        <pre>{formatJson(eventPayload(event) || event.content || event)}</pre>
      </details>
    </div>
  );
}

function renderProgressBlock(
  block: ExecutionTraceRenderBlock,
  expanded: boolean,
  toggleExpanded: () => void,
) {
  const stages = block.stages || [];
  const displayStages = expanded ? stages : stages.slice(-TRACE_STAGE_COLLAPSED_COUNT);
  const hiddenStageCount = Math.max(0, stages.length - displayStages.length);
  const currentStage =
    [...stages]?.reverse()?.find?.((stage) => stage.status === 'running') ||
    stages[stages.length - 1];
  const title =
    block.status === 'done'
      ? '已回答完成'
      : block.status === 'error'
      ? '执行过程异常'
      : currentStage
      ? traceStageTitle(currentStage)
      : '正在处理请求';
  const thinkingText = collapseWhitespace(block.text || '');
  return (
    <div className={`skill-factory-trace-panel ${block.status || 'running'}`} key={block.key}>
      <button className="skill-factory-trace-panel-head" onClick={toggleExpanded} type="button">
        <span className="skill-factory-trace-panel-icon">
          <ThunderboltOutlined />
        </span>
        <span className="skill-factory-trace-panel-title">{title}</span>
        <Text type="secondary">{formatTime(block.timestamp)}</Text>
        <DownOutlined className={`skill-factory-trace-panel-arrow${expanded ? ' open' : ''}`} />
      </button>
      {expanded && thinkingText ? (
        <details className="skill-factory-trace-thinking" open>
          <summary>查看完整思考摘要</summary>
          <pre>{thinkingText}</pre>
        </details>
      ) : null}
      {hiddenStageCount ? (
        <div className="skill-factory-trace-hidden-count">已收起 {hiddenStageCount} 个较早步骤</div>
      ) : null}
      <div className="skill-factory-trace-stage-list">
        {displayStages.map((stage) => renderTraceStage(stage, expanded))}
      </div>
    </div>
  );
}

export const ExecutionTraceLayer: React.FC<{
  events: SkillFactoryCodingEvent[];
  blockType?: ExecutionTraceRenderBlock['type'];
  pendingFinalAnswer?: boolean;
  pendingTimestamp?: number;
}> = ({ events, blockType, pendingFinalAnswer = false, pendingTimestamp }) => {
  const [expandedTraceKeys, setExpandedTraceKeys] = useState<Record<string, boolean>>({});
  const blocks = useMemo(
    () =>
      buildExecutionTraceBlocks(events, pendingFinalAnswer, pendingTimestamp)?.filter?.(
        (block) => !blockType || block.type === blockType,
      ),
    [blockType, events, pendingFinalAnswer, pendingTimestamp],
  );
  if (!blocks.length) return null;
  return (
    <div className="skill-factory-message-layer execution">
      <div className="skill-factory-debug-block-list">
        {blocks.map((block) =>
          block.type === 'progress'
            ? renderProgressBlock(block, Boolean(expandedTraceKeys[block.key]), () =>
                setExpandedTraceKeys((current) => ({
                  ...current,
                  [block.key]: !current[block.key],
                })),
              )
            : renderArtifactBlock(block),
        )}
      </div>
    </div>
  );
};

function businessEventTitle(event: SkillFactoryCodingEvent): string {
  const payload = eventPayload(event);
  const payloadType = event.payloadType || textOf(payload?.type);
  if (payloadType === 'COMPONENT_ASSET_DRAFT') return '组件资产草稿已更新';
  if (payloadType === 'COMPONENT_ASSET_VALIDATION') return '组件资产校验结果';
  if (payloadType === 'COMPONENT_ASSET_PREVIEW') return '组件资产预览结果';
  if (payloadType === 'COMPONENT_ASSET_SAVE_PREPARED') return '待确认保存参数';
  return event.title || payloadType || event.eventType;
}

function businessEventSummary(event: SkillFactoryCodingEvent): string {
  const payload = eventPayload(event);
  const content = eventContent(event);
  const payloadContent = recordOf(payload?.content);
  return (
    trimTraceText(
      textOf(content.summary) ||
        textOf(payloadContent?.summary) ||
        textOf(content.message) ||
        textOf(payloadContent?.message) ||
        eventText(event),
      180,
    ) || '结构化业务事件已处理，右侧面板会同步更新相关草稿。'
  );
}

export const BusinessInteractionLayer: React.FC<{
  events: SkillFactoryCodingEvent[];
  onOpenReview?: OpenAuthoringReview;
  changeReviewStatuses?: Record<string, ChangeReviewStatus>;
}> = ({ events, onOpenReview, changeReviewStatuses }) =>
  events.length ? (
    <div className="skill-factory-message-layer business">
      {events.map((event, index) => {
        const payload = eventPayload(event);
        const payloadType = textOf(event.payloadType || payload?.payloadType || payload?.type);
        const changeSetId = codingEventIdentity(event);
        const reviewStatus = changeReviewStatuses?.[changeSetId];
        const reviewAvailable = Boolean(onOpenReview && reviewStatus);
        const operationCount = Array.isArray(recordOf(payload?.content)?.operations)
          ? (recordOf(payload?.content)?.operations as unknown[])?.length
          : Array.isArray(payload?.operations)
          ? (payload?.operations as unknown[])?.length
          : Array.isArray(recordOf(payload?.content)?.changedPaths)
          ? (recordOf(payload?.content)?.changedPaths as unknown[])?.length
          : Array.isArray(payload?.changedPaths)
          ? (payload?.changedPaths as unknown[])?.length
          : 0;
        if (
          payloadType === 'FORM_PATCH_PROPOSED' ||
          payloadType === 'CAPABILITY_DRAFT_SNAPSHOT' ||
          payloadType === 'CAPABILITY_DRAFT_PATCH'
        ) {
          return (
            <button
              className="skill-factory-change-summary"
              disabled={!reviewAvailable}
              key={changeSetId || `${event.eventType}-${index}`}
              onClick={() => onOpenReview?.(changeSetId, event)}
              type="button"
            >
              <span>
                <strong>
                  {operationCount ? `将修改 ${operationCount} 个表单字段` : '表单修改建议已生成'}
                </strong>
                <small>{businessEventSummary(event)}</small>
              </span>
              <Tag
                color={
                  !reviewAvailable
                    ? 'default'
                    : reviewStatus === 'APPLIED'
                    ? 'success'
                    : reviewStatus === 'DISCARDED'
                    ? 'default'
                    : 'warning'
                }
              >
                {!reviewAvailable
                  ? '已过期'
                  : reviewStatus === 'APPLIED'
                  ? '已应用'
                  : reviewStatus === 'DISCARDED'
                  ? '已丢弃'
                  : '查看修改'}
              </Tag>
            </button>
          );
        }
        return (
          <div
            className="skill-factory-a2ui-card compact"
            key={changeSetId || `${event.eventType}-${index}`}
          >
            <div className="skill-factory-a2ui-card-head">
              <strong>{businessEventTitle(event)}</strong>
              <Tag>{event.payloadType || event.eventType}</Tag>
            </div>
            <div className="skill-factory-a2ui-event-summary">{businessEventSummary(event)}</div>
            <details className="skill-factory-trace-raw">
              <summary>查看结构化数据</summary>
              <pre>{jsonStringify(eventPayload(event) || event.content || {}, null, 2)}</pre>
            </details>
          </div>
        );
      })}
    </div>
  ) : null;

export const SkillFactoryChatMessageList: React.FC<{
  items: SkillFactoryAuthoringChatItem[];
  renderAssistantMessage?: (message: SkillFactoryAuthoringMessage) => React.ReactNode;
  onOpenReview?: OpenAuthoringReview;
  changeReviewStatuses?: Record<string, ChangeReviewStatus>;
}> = ({ items, renderAssistantMessage, onOpenReview, changeReviewStatuses }) => (
  <>
    {items.map((item) =>
      item.type === 'assistant' ? (
        <div className="skill-factory-chat-message assistant" key={item.message?.messageId}>
          <div className="skill-factory-chat-avatar">AI</div>
          <div className="skill-factory-chat-body">
            <div className="skill-factory-chat-meta">
              <Text type="secondary">{formatTime(item.message?.timestamp)}</Text>
              <Tag
                color={
                  item.message?.status === 'error'
                    ? 'error'
                    : item.message?.status === 'cancelled'
                    ? 'default'
                    : 'blue'
                }
              >
                {item.message?.status === 'done'
                  ? '已完成'
                  : item.message?.status === 'error'
                  ? '失败'
                  : item.message?.status === 'cancelled'
                  ? '已停止'
                  : '生成中'}
              </Tag>
              <Text className="skill-factory-chat-message-id" code title={item.message?.messageId}>
                {item.message?.messageId}
              </Text>
            </div>
            <div className="skill-factory-assistant-message">
              {renderAssistantMessage ? (
                renderAssistantMessage(item.message)
              ) : (
                <>
                  <ExecutionTraceLayer
                    blockType="progress"
                    events={item.message?.executionTrace}
                    pendingFinalAnswer={
                      item.message.status === 'streaming' && !item.message.answerText
                    }
                    pendingTimestamp={item.message?.timestamp}
                  />
                  <AnswerLayer text={item.message?.answerText} status={item.message?.status} />
                  <ExecutionTraceLayer blockType="artifact" events={item.message?.executionTrace} />
                  <BusinessInteractionLayer
                    events={item.message?.businessEvents}
                    onOpenReview={onOpenReview}
                    changeReviewStatuses={changeReviewStatuses}
                  />
                </>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className={`skill-factory-chat-message ${item.turn?.role}`} key={item.turn?.id}>
          <div className="skill-factory-chat-avatar">{authoringTurnAvatarLabel(item.turn)}</div>
          <div className="skill-factory-chat-body">
            <div className="skill-factory-chat-meta">
              {item.turn?.role === 'user' ? (
                <Text type="secondary">{authoringTurnActorLabel(item.turn)}</Text>
              ) : null}
              <Text type="secondary">{formatTime(item.turn?.timestamp)}</Text>
            </div>
            <div
              className={`skill-factory-chat-bubble${
                item.turn?.role === 'assistant' ? ' markdown' : ''
              }`}
            >
              {item.turn?.role === 'assistant' ? (
                <ReactMarkdown
                  className="skill-factory-markdown-answer"
                  remarkPlugins={[remarkGfm]}
                >
                  {item.turn?.text}
                </ReactMarkdown>
              ) : (
                item.turn?.text
              )}
            </div>
          </div>
        </div>
      ),
    )}
  </>
);

function guidePromptKey(prompt: AuthoringGuidePrompt, index: number): string {
  return prompt.key || prompt.text || prompt.sendMsg || `guide-${index}`;
}

function guidePromptText(prompt: AuthoringGuidePrompt): string {
  return textOf(prompt.text || prompt.sendMsg);
}

function enabledGuideConfig(config?: AuthoringGuideConfig): AuthoringGuideConfig | undefined {
  if (!config?.enabled) return undefined;
  return config;
}

const AuthoringGuidePromptButton: React.FC<{
  prompt: AuthoringGuidePrompt;
  index: number;
  variant?: 'chip' | 'suggestion';
  disabled?: boolean;
  onClick?: (prompt: AuthoringGuidePrompt) => void | Promise<void>;
}> = ({ prompt, index, variant = 'chip', disabled, onClick }) => {
  const label = guidePromptText(prompt);
  if (!label) return null;
  const actionType = textOf(prompt.actionType || GUIDE_ACTION_SEND)?.toUpperCase?.();
  return (
    <Button
      size="small"
      disabled={disabled}
      className={`skill-factory-authoring-guide-action ${variant}`}
      onClick={() => onClick?.(prompt)}
    >
      <span className="skill-factory-authoring-guide-action-text">{label}</span>
      {actionType === GUIDE_ACTION_FILL_INPUT ? (
        <Text type="secondary" className="skill-factory-authoring-guide-action-mode">
          填入
        </Text>
      ) : null}
      {variant === 'suggestion' ? (
        <span className="skill-factory-authoring-guide-action-arrow">→</span>
      ) : null}
    </Button>
  );
};

export const AuthoringGuidePromptList: React.FC<{
  prompts?: AuthoringGuidePrompt[];
  variant?: 'chip' | 'suggestion';
  disabled?: boolean;
  onPromptClick?: (prompt: AuthoringGuidePrompt) => void | Promise<void>;
}> = ({ prompts, variant = 'chip', disabled, onPromptClick }) => {
  const visiblePrompts = (prompts || []).filter((prompt) => guidePromptText(prompt));
  if (!visiblePrompts.length) return null;
  return (
    <div className={`skill-factory-authoring-guide-prompts ${variant}`}>
      {visiblePrompts.map((prompt, index) => (
        <AuthoringGuidePromptButton
          key={guidePromptKey(prompt, index)}
          prompt={prompt}
          index={index}
          variant={variant}
          disabled={disabled}
          onClick={onPromptClick}
        />
      ))}
    </div>
  );
};

const AuthoringGuideEmpty: React.FC<{
  config?: AuthoringGuideConfig;
  fallback?: React.ReactNode;
  disabled?: boolean;
  onPromptClick?: (prompt: AuthoringGuidePrompt) => void | Promise<void>;
}> = ({ config, fallback, disabled, onPromptClick }) => {
  const guideConfig = enabledGuideConfig(config);
  if (!guideConfig || !guideConfig.quickPrompts?.length) {
    return <div className="skill-factory-chat-empty">{fallback}</div>;
  }
  return (
    <div className="skill-factory-authoring-guide-empty">
      <AuthoringGuidePromptList
        prompts={guideConfig.quickPrompts}
        variant="suggestion"
        disabled={disabled}
        onPromptClick={onPromptClick}
      />
    </div>
  );
};

/**
 * 底层 Shell 仅负责基础布局，不保证消息聚合、结构化事件分层和会话选择一致性。
 */
export const SkillFactoryAuthoringChatShell: React.FC<SkillFactoryAuthoringChatShellProps> = ({
  title,
  extra,
  listRef,
  listClassName,
  messagesNode,
  emptyText = '暂无会话',
  authoringGuideConfig,
  onGuidePromptClick,
  quickActions,
  toolbarExtra,
  input,
  onInputChange,
  onPressEnter,
  onSend,
  onStop,
  loading,
  disabled,
  stopDisabled,
  sendDisabled,
  placeholder,
  sidePanel,
}) => (
  <div className={`skill-factory-card-layout${sidePanel ? '' : ' single'}`}>
    <Card
      title={title}
      className="skill-factory-chat-card"
      extra={extra}
      bodyStyle={AUTHORING_CHAT_CARD_BODY_STYLE}
    >
      <div className="skill-factory-chat-surface">
        <div
          className={`skill-factory-chat-list${listClassName ? ` ${listClassName}` : ''}`}
          ref={listRef}
        >
          {messagesNode || (
            <AuthoringGuideEmpty
              config={authoringGuideConfig}
              fallback={emptyText}
              disabled={disabled || loading}
              onPromptClick={onGuidePromptClick}
            />
          )}
        </div>
        <div className="skill-factory-chat-composer">
          <div className="skill-factory-chat-prompt-row">
            <AuthoringGuidePromptList
              prompts={enabledGuideConfig(authoringGuideConfig)?.composerPrompts}
              disabled={disabled || loading}
              onPromptClick={onGuidePromptClick}
            />
            {quickActions ? (
              <div className="skill-factory-quick-prompts">{quickActions}</div>
            ) : null}
          </div>
          {toolbarExtra}
          <div className="skill-factory-chat-input-row">
            <TextArea
              value={input}
              onChange={(event) => onInputChange(event.target.value)}
              onPressEnter={onPressEnter}
              autoSize={{ minRows: 4, maxRows: 8 }}
              disabled={disabled}
              placeholder={placeholder}
            />
            <Space>
              <Button type="primary" loading={loading} disabled={sendDisabled} onClick={onSend}>
                发送
              </Button>
              <Button icon={<StopOutlined />} disabled={stopDisabled} onClick={onStop}>
                停止
              </Button>
            </Space>
          </div>
        </div>
      </div>
    </Card>
    {sidePanel}
  </div>
);

function shortSessionId(sessionId?: string): string {
  const text = sessionId || '';
  if (text.length <= 18) return text;
  return `${text.slice(0, 10)}...${text.slice(-6)}`;
}

function shortSessionTitle(title?: string): string {
  const characters = Array.from(title || '');
  if (characters.length <= SESSION_TITLE_MAX_CHARACTERS) return characters.join('');
  return `${characters?.slice(0, SESSION_TITLE_MAX_CHARACTERS)?.join?.('')}…`;
}

function sessionOptionLabel(session: AuthoringSessionSummary): string {
  const name =
    shortSessionTitle(session.title) || shortSessionId(session.sessionId) || '未命名会话';
  const actor = authoringSessionActorLabel(session);
  const time = formatTime(session.lastMessageTime || session.updateTime || session.createTime);
  return [name, actor, time]?.filter(Boolean)?.join?.(' · ');
}

function isGuideOnlyConversation(chat: UseSkillFactoryChatStreamResult): boolean {
  const onlyTurn = chat.turns?.[0];
  return (
    chat.turns.length === 1 &&
    onlyTurn?.role === 'assistant' &&
    textOf(onlyTurn.id).startsWith(GUIDE_TURN_ID_PREFIX) &&
    !chat.messages.length
  );
}

const AuthoringSessionSelector: React.FC<{ chat: UseSkillFactoryChatStreamResult }> = ({
  chat,
}) => (
  <Select
    className="skill-factory-chat-session-selector"
    size="small"
    value={chat.selectedSessionId || undefined}
    placeholder="选择会话"
    loading={chat.historyLoading}
    disabled={chat.historyLoading || chat.loading || Boolean(chat.sessionDisabledReason)}
    options={(chat.sessionOptions || []).map((session) => ({
      label: sessionOptionLabel(session),
      value: session.sessionId,
    }))}
    onChange={(value) => chat.selectSession(String(value))}
  />
);

export const SkillFactoryAuthoringChat: React.FC<{
  title: React.ReactNode;
  chat: UseSkillFactoryChatStreamResult;
  extra?: React.ReactNode;
  sidePanel?: React.ReactNode;
  placeholder?: string;
  messagesNode?: React.ReactNode;
  renderAssistantMessage?: (message: SkillFactoryAuthoringMessage) => React.ReactNode;
  onOpenReview?: OpenAuthoringReview;
  changeReviewStatuses?: Record<string, ChangeReviewStatus>;
  quickActions?: React.ReactNode;
  toolbarExtra?: React.ReactNode;
  emptyText?: React.ReactNode;
}> = ({
  title,
  chat,
  extra,
  sidePanel,
  placeholder,
  messagesNode,
  renderAssistantMessage,
  onOpenReview,
  changeReviewStatuses,
  quickActions,
  toolbarExtra,
  emptyText,
}) => {
  const listRef = useRef<HTMLDivElement>(null);
  const followLatestRef = useRef(true);
  const lastScrollTopRef = useRef(0);
  const scrollStateRef = useRef({
    sessionId: '',
    itemCount: 0,
    renderRevision: 0,
  });

  useEffect(() => {
    const list = listRef.current;
    if (!list) return undefined;
    const handleScroll = () => {
      const scrollTop = list.scrollTop;
      const distanceToBottom = list.scrollHeight - scrollTop - list.clientHeight;
      if (scrollTop < lastScrollTopRef.current - 1) {
        followLatestRef.current = false;
      } else if (distanceToBottom <= CHAT_FOLLOW_BOTTOM_THRESHOLD) {
        followLatestRef.current = true;
      }
      lastScrollTopRef.current = scrollTop;
    };
    list.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();
    return () => list.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const previous = scrollStateRef.current;
    const next = {
      sessionId: chat.selectedSessionId,
      itemCount: chat.chatItems?.length,
      renderRevision: chat.renderRevision,
    };
    scrollStateRef.current = next;
    const sessionChanged = next.sessionId !== previous.sessionId;
    if (sessionChanged) {
      followLatestRef.current = true;
    }
    if (
      !sessionChanged &&
      next.itemCount === previous.itemCount &&
      next.renderRevision === previous.renderRevision
    ) {
      return;
    }
    if (!followLatestRef.current) return;
    list.scrollTo({ top: list.scrollHeight, behavior: 'auto' });
    lastScrollTopRef.current = list.scrollTop;
  }, [chat.selectedSessionId, chat.chatItems?.length, chat.renderRevision]);

  const handlePressEnter = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.shiftKey) return;
    event.preventDefault();
    chat.send();
  };
  const guideOnly = isGuideOnlyConversation(chat);

  return (
    <SkillFactoryAuthoringChatShell
      title={title}
      extra={
        <div className="skill-factory-chat-header-extra">
          {extra ? <div className="skill-factory-chat-header-status">{extra}</div> : null}
          <AuthoringSessionSelector chat={chat} />
        </div>
      }
      listRef={listRef}
      listClassName={guideOnly ? 'guide-only' : undefined}
      messagesNode={
        messagesNode ||
        (chat.chatItems?.length ? (
          <div className={guideOnly ? 'skill-factory-guide-conversation' : undefined}>
            <SkillFactoryChatMessageList
              items={chat.chatItems}
              renderAssistantMessage={renderAssistantMessage}
              onOpenReview={onOpenReview}
              changeReviewStatuses={changeReviewStatuses}
            />
            {guideOnly ? (
              <AuthoringGuidePromptList
                prompts={enabledGuideConfig(chat.authoringGuideConfig)?.quickPrompts}
                variant="suggestion"
                disabled={
                  chat.historyLoading || chat.loading || Boolean(chat.sessionDisabledReason)
                }
                onPromptClick={chat.runGuidePrompt}
              />
            ) : null}
          </div>
        ) : null)
      }
      emptyText={emptyText}
      authoringGuideConfig={chat.authoringGuideConfig}
      onGuidePromptClick={chat.runGuidePrompt}
      quickActions={quickActions}
      toolbarExtra={toolbarExtra}
      input={chat.input}
      onInputChange={chat.setInput}
      onPressEnter={handlePressEnter}
      onSend={() => chat.send()}
      onStop={chat.stop}
      loading={chat.loading}
      disabled={chat.historyLoading || chat.loading || Boolean(chat.sessionDisabledReason)}
      stopDisabled={!chat.loading}
      sendDisabled={
        !chat.input?.trim?.() ||
        chat.historyLoading ||
        chat.loading ||
        Boolean(chat.sessionDisabledReason)
      }
      placeholder={
        chat.historyLoading ? '正在加载会话历史...' : chat.sessionDisabledReason || placeholder
      }
      sidePanel={sidePanel}
    />
  );
};
