import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAui,
  useExternalStoreRuntime,
  type AppendMessage,
} from '@assistant-ui/react';
import { useCallback, useMemo, useRef, useState } from 'react';

import { toAssistantMessage } from '../assistantChat';
import { copyText } from '../clipboard.mjs';
import { appendComposerDraft } from '../composerDraft.mjs';
import { chatErrorPresentation } from '../errorPresentation';
import type {
  ChatCard,
  ChatModelMessage,
  ChatToolCall,
  ComposerDraftEffect,
  Message,
} from '../productApi';
import {
  LegacyApplications,
  OrderedApplication,
  UnassignedApplications,
} from './ChatApplications';
import { MarkdownContent } from './MarkdownContent';

type AssistantThreadProps = {
  messages: Message[];
  isRunning: boolean;
  isSendDisabled: boolean;
  error: string;
  unassignedCards: ChatCard[];
  onSend: (text: string) => Promise<void>;
  onCardUpdate: (card: ChatCard) => void;
  onCardActionStateChange: (cardId: string, active: boolean) => void;
  renderMessageExtras: (message: Message) => React.ReactNode;
  threadTail?: React.ReactNode;
  onComposerError: (message: string) => void;
};

type ProcessItem =
  | { kind: 'model'; sequence: number; value: ChatModelMessage }
  | { kind: 'tool'; sequence: number; value: ChatToolCall };

const prettyJson = (value: unknown) => {
  if (value === undefined) return '暂无结果';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return '结果无法展示';
  }
};

const toolStateLabel = (tool: ChatToolCall) => {
  if (tool.lifecycleStatus === 'running') return '调用中';
  if (tool.lifecycleStatus === 'raised') return '调用异常';
  if (tool.toolMessageStatus === 'error') return '工具返回错误';
  return '调用已返回';
};

function ToolProcess({ tool, index }: { tool: ChatToolCall; index: number }) {
  const [open, setOpen] = useState(false);
  return <details
    className={`tool-process ${tool.lifecycleStatus}`}
    open={open}
  >
    <summary onClick={(event) => {
      event.preventDefault();
      setOpen(value => !value);
    }}>
      <span className="tool-process-index">{index}</span>
      <strong>{tool.name}</strong>
      <span className="tool-process-id">{tool.toolCallId}</span>
      <span className="tool-process-state">{toolStateLabel(tool)}</span>
      {tool.durationMs !== undefined ? <span>{(tool.durationMs / 1000).toFixed(1)}s</span> : null}
    </summary>
    {open ? <ToolProcessBody tool={tool} /> : null}
  </details>;
}

function ToolProcessBody({ tool }: { tool: ChatToolCall }) {
  const [copyState, setCopyState] = useState<{
    resultText: string;
    status: 'copied' | 'failed';
  } | null>(null);
  const formattedResult = useMemo(() => {
    if (tool.result === undefined) return { text: '暂无返回结果', copyable: false };
    if (typeof tool.result === 'string') return { text: tool.result, copyable: true };
    try {
      const text = JSON.stringify(tool.result, null, 2);
      return typeof text === 'string'
        ? { text, copyable: true }
        : { text: '返回结果无法格式化', copyable: false };
    } catch {
      return { text: '返回结果无法格式化', copyable: false };
    }
  }, [tool.result]);
  const handleCopy = useCallback(async () => {
    if (!formattedResult.copyable) return;
    const copied = await copyText(formattedResult.text);
    setCopyState({
      resultText: formattedResult.text,
      status: copied ? 'copied' : 'failed',
    });
  }, [formattedResult]);
  const copyStatus = copyState?.resultText === formattedResult.text
    ? copyState.status
    : 'idle';

  return <div className="tool-process-grid">
    <section><h4>输入参数</h4><pre>{prettyJson(tool.arguments)}</pre></section>
    <section className="tool-result">
      <header>
        <h4>返回结果</h4>
        {tool.result !== undefined
          ? <button type="button" disabled={!formattedResult.copyable} onClick={() => void handleCopy()}>
            复制完整结果
          </button>
          : null}
      </header>
      <pre>{formattedResult.text}</pre>
      <span className={`copy-feedback ${copyStatus}`} aria-live="polite">
        {copyStatus === 'copied'
          ? '已复制'
          : copyStatus === 'failed'
            ? '复制失败，请手动选择结果内容'
            : ''}
      </span>
      {tool.businessSuccess !== undefined && tool.businessSuccess !== null
        ? <p className={tool.businessSuccess ? 'business-success' : 'business-failure'}>
          {tool.businessSuccess ? '业务确认成功' : '业务确认未成功'}
        </p>
        : null}
      {tool.errorCode ? <p className="tool-error-code">错误码：{tool.errorCode}</p> : null}
    </section>
  </div>;
}

function ModelProcess({ message, showProcessText = true }: {
  message: ChatModelMessage;
  showProcessText?: boolean;
}) {
  return <section className="model-process">
    {message.reasoning ? <div><h4>思考过程</h4><MarkdownContent markdown={message.reasoning} /></div> : null}
    {showProcessText && message.phase === 'process' && message.text
      ? <div><h4>过程输出</h4><MarkdownContent markdown={message.text} /></div>
      : null}
  </section>;
}

function ExecutionPanel({ message }: { message: Message }) {
  const execution = message.execution;
  const hasOrderedText = Boolean(message.parts?.some(part => part.type === 'text'));
  const legacyReasoning = !execution ? message.reasoning : '';
  const items = useMemo<ProcessItem[]>(() => {
    if (!execution) return [];
    return [
      ...execution.modelMessages
        .filter(value => Boolean(value.reasoning || (!hasOrderedText && value.phase === 'process' && value.text)))
        .map(value => ({ kind: 'model' as const, sequence: value.sequence, value })),
      ...execution.toolCalls.map(value => ({ kind: 'tool' as const, sequence: value.sequence, value })),
    ].sort((left, right) => left.sequence - right.sequence);
  }, [execution, hasOrderedText]);
  const legacyTools = !execution ? message.tools ?? [] : [];
  const hasProcess = Boolean(items.length || legacyReasoning || legacyTools.length || message.delivery === 'failed');
  const running = message.delivery === 'running';
  const [manualOpen, setManualOpen] = useState<boolean | null>(null);
  if (!hasProcess) return null;
  return <details
    className="execution-panel"
    open={manualOpen ?? running}
  >
    <summary onClick={(event) => {
      event.preventDefault();
      setManualOpen(!(manualOpen ?? running));
    }}>
      <span>{running ? '执行中' : '执行过程'}</span>
      <span>{execution?.toolCalls.length ?? message.tools?.length ?? 0} 次工具调用</span>
    </summary>
    <div className="execution-panel-body">
      {message.delivery === 'failed'
        ? <p className="execution-error">失败原因：{chatErrorPresentation(message.errorCode)}</p>
        : null}
      {legacyReasoning ? <ModelProcess message={{
        sequence: 1,
        messageId: '',
        text: '',
        reasoning: legacyReasoning,
        phase: 'process',
      }} /> : null}
      {legacyTools.map((tool, index) => <p className="legacy-tool-process" key={`${tool}:${index}`}>
        调用工具：{tool}
      </p>)}
      {items.map((item, index) => item.kind === 'model'
        ? <ModelProcess
          key={`model:${item.value.messageId}:${item.sequence}`}
          message={item.value}
          showProcessText={!hasOrderedText}
        />
        : <ToolProcess
          key={`tool:${item.value.toolCallId}`}
          tool={item.value}
          index={items.slice(0, index + 1).filter(candidate => candidate.kind === 'tool').length}
        />)}
    </div>
  </details>;
}

function UserMessage({ message }: { message: Message }) {
  return <MessagePrimitive.Root className="aui-message aui-user-message">
    <div className="aui-user-bubble">{message.text}</div>
  </MessagePrimitive.Root>;
}

function AssistantMessage({
  message,
  renderMessageExtras,
  onCardUpdate,
  onCardActionStateChange,
  onComposerDraft,
}: {
  message: Message;
  renderMessageExtras: AssistantThreadProps['renderMessageExtras'];
  onCardUpdate: AssistantThreadProps['onCardUpdate'];
  onCardActionStateChange: AssistantThreadProps['onCardActionStateChange'];
  onComposerDraft: (effect: ComposerDraftEffect) => void;
}) {
  const deliveryLabel = message.delivery === 'waiting_action'
    ? '等待你确认'
    : message.delivery === 'completed'
      ? '已完成'
      : message.delivery === 'failed'
        ? '执行失败 · 未自动重试'
        : message.delivery === 'running'
          ? '执行中'
          : message.delivery === 'unconfirmed'
            ? '结果待确认 · 不会自动重试'
            : '';
  return <MessagePrimitive.Root className="aui-message aui-assistant-message">
    <div className="aui-assistant-avatar" aria-hidden="true">AI</div>
    <div className="aui-assistant-content">
      {deliveryLabel ? <p className={`assistant-delivery ${message.delivery ?? ''}`}>{deliveryLabel}</p> : null}
      <ExecutionPanel message={message} />
      {message.parts?.length
        ? message.parts.map(part => part.type === 'text'
          ? <section className="assistant-answer" key={part.id}><MarkdownContent markdown={part.text} /></section>
          : <OrderedApplication
            key={part.id}
            part={part}
            onCardUpdate={onCardUpdate}
            onCardActionStateChange={onCardActionStateChange}
            onComposerDraft={onComposerDraft}
          />)
        : message.text
          ? <section className="assistant-answer"><MarkdownContent markdown={message.text} /></section>
          : null}
      {renderMessageExtras(message)}
      {message.legacyCards?.length ? <LegacyApplications
        cards={message.legacyCards}
        onCardUpdate={onCardUpdate}
        onCardActionStateChange={onCardActionStateChange}
        onComposerDraft={onComposerDraft}
      /> : null}
    </div>
  </MessagePrimitive.Root>;
}

function ChatComposer() {
  return <ComposerPrimitive.Root className="aui-composer">
    <ComposerPrimitive.Input
      aria-label="消息"
      placeholder="输入消息，描述你想完成的工作"
      submitMode="enter"
      unstable_insertNewlineOnTouchEnter
    />
    <ComposerPrimitive.Send className="aui-send" aria-label="发送消息">发送</ComposerPrimitive.Send>
  </ComposerPrimitive.Root>;
}

function ThreadBody({
  messages,
  error,
  renderMessageExtras,
  onComposerError,
  threadTail,
  unassignedCards,
  onCardUpdate,
  onCardActionStateChange,
}: Omit<AssistantThreadProps, 'onSend' | 'isSendDisabled'>) {
  const aui = useAui();
  const consumedEffects = useRef(new Set<string>());
  const applyComposerDraft = useCallback((effect: ComposerDraftEffect) => {
    if (effect.type !== 'COMPOSER_DRAFT' || effect.mode !== 'APPEND'
      || !effect.requestId || !effect.text || consumedEffects.current.has(effect.requestId)) return;
    const composer = aui.composer();
    const next = appendComposerDraft(composer.getState().text, effect.text);
    if (next === null) {
      onComposerError('回填内容与当前输入合并后超过 4000 字，未覆盖已有输入。');
      return;
    }
    composer.setText(next);
    consumedEffects.current.add(effect.requestId);
  }, [aui, onComposerError]);

  const messagesById = useMemo(() => new Map(messages.map(message => [message.id, message])), [messages]);
  return <ThreadPrimitive.Root className="aui-thread">
      <ThreadPrimitive.Viewport
        className="aui-thread-viewport"
        autoScroll
        turnAnchor="bottom"
        scrollToBottomOnInitialize
        scrollToBottomOnRunStart
        scrollToBottomOnThreadSwitch
      >
        <ThreadPrimitive.Messages>
          {({ message }) => {
            const source = messagesById.get(message.id);
            if (!source) return null;
            return source.role === 'user'
              ? <UserMessage message={source} />
              : <AssistantMessage
                message={source}
                renderMessageExtras={renderMessageExtras}
                onCardUpdate={onCardUpdate}
                onCardActionStateChange={onCardActionStateChange}
                onComposerDraft={applyComposerDraft}
              />;
          }}
        </ThreadPrimitive.Messages>
        {threadTail}
        <UnassignedApplications
          cards={unassignedCards}
          onCardUpdate={onCardUpdate}
          onCardActionStateChange={onCardActionStateChange}
          onComposerDraft={applyComposerDraft}
        />
        <ThreadPrimitive.ViewportFooter className="aui-thread-footer">
          {error ? <p className="chat-error" role="alert">{error}</p> : null}
          <ChatComposer />
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>;
}

export function AssistantThread(props: AssistantThreadProps) {
  const onNew = useCallback(async (message: AppendMessage) => {
    const text = message.content
      .filter((part): part is Extract<(typeof message.content)[number], { type: 'text' }> => part.type === 'text')
      .map(part => part.text)
      .join('\n')
      .trim();
    if (!text) throw new Error('仅支持文本消息');
    await props.onSend(text);
  }, [props.onSend]);

  const runtime = useExternalStoreRuntime({
    messages: props.messages,
    convertMessage: toAssistantMessage,
    isRunning: props.isRunning,
    isSendDisabled: props.isSendDisabled,
    onNew,
  });

  return <AssistantRuntimeProvider runtime={runtime}>
    <ThreadBody {...props} />
  </AssistantRuntimeProvider>;
}
