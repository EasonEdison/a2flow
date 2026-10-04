import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, client } from '../api/client';
import { createUuidV4 } from '../secureUuid.mjs';
import {
  object,
  string,
  type JsonObject,
  type RunItem,
  type Session,
  type WireView,
  type Workflow,
} from '../api/contracts';
import {
  beginRead,
  canDispatch,
  isCurrentRead,
  isDefinitelyRejected,
  stoppedRunAcceptsUpdate,
  type ControlKind,
  type PendingControl,
} from './controlState';

const errorText = (error: unknown) => {
  if (error instanceof ApiError) {
    const messages: Record<string, string> = {
      RUN_STOPPED: '此运行已停止，卡片只读。',
      TRUSTED_CONTEXT_REQUIRED: '请通过受认证入口打开页面。',
      CAPACITY_EXHAUSTED: '执行容量已满，请稍后查看请求状态。',
      CONTROL_NOT_FOUND: '请求尚未分配运行，请稍后查看。',
    };
    return messages[error.code] ?? `服务暂不可用（${error.code}）`;
  }
  return error instanceof Error ? error.message : '服务暂不可用';
};

export function useRuntime(enabled: boolean) {
  const [session, setSession] = useState<Session | null>(null);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [view, setView] = useState<WireView | null>(null);
  const [runId, setRunId] = useState<string | null>(
    new URLSearchParams(location.search).get('run'),
  );
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(enabled);
  const [pendingControls, setPendingControls] = useState<PendingControl[]>([]);
  const [uncertain, setUncertain] = useState(false);

  const storage = useRef<string | null>(null);
  const controls = useRef<PendingControl[]>([]);
  const locks = useRef(new Set<ControlKind>());
  const stoppedRunIds = useRef(new Set<string>());
  const readGenerations = useRef(new Map<string, number>());
  const current = useRef(runId);
  const alive = useRef(true);
  current.current = runId;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const persistControls = useCallback((next: PendingControl[]) => {
    controls.current = next;
    setPendingControls(next);
    if (!storage.current) {
      return;
    }
    if (next.length) {
      sessionStorage.setItem(storage.current, JSON.stringify(next));
    } else {
      sessionStorage.removeItem(storage.current);
    }
  }, []);

  const addControl = useCallback(
    (control: PendingControl) => {
      persistControls([...controls.current, control]);
    },
    [persistControls],
  );

  const removeControl = useCallback(
    (id: string) => {
      persistControls(controls.current.filter((control) => control.id !== id));
    },
    [persistControls],
  );

  const select = useCallback((id: string | null) => {
    setView(null);
    setRunId(id);
    const url = new URL(location.href);
    if (id) {
      url.searchParams.set('run', id);
    } else {
      url.searchParams.delete('run');
    }
    history.replaceState(null, '', url);
  }, []);

  const refreshReadModel = useCallback(async (id: string) => {
    const generation = beginRead(readGenerations.current, id);
    try {
      const next = await client.view(id);
      if (
        alive.current &&
        current.current === id &&
        isCurrentRead(readGenerations.current, id, generation)
      ) {
        setView(next);
      }
      const history = await client.runs();
      if (alive.current && isCurrentRead(readGenerations.current, id, generation)) {
        setRuns(history.items);
      }
    } catch (readError) {
      if (alive.current) {
        setError(`${errorText(readError)}；写请求已受理，展示稍后刷新。`);
      }
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const abort = new AbortController();

    void (async () => {
      try {
        const identity = await client.session(abort.signal);
        if (abort.signal.aborted) {
          return;
        }
        setSession(identity);
        storage.current = `a2flow.pending.v2:${identity.environment}:${identity.userId}`;

        const saved = sessionStorage.getItem(storage.current);
        if (saved) {
          try {
            const parsed = JSON.parse(saved);
            if (
              Array.isArray(parsed) &&
              parsed.every(
                (control) =>
                  control &&
                  typeof control.id === 'string' &&
                  ['start', 'action', 'stop', 'restart'].includes(control.kind),
              )
            ) {
              persistControls(parsed);
            }
          } catch {
            sessionStorage.removeItem(storage.current);
          }
        }

        const [definitions, history] = await Promise.all([
          client.workflows(abort.signal),
          client.runs(undefined, abort.signal),
        ]);
        if (!abort.signal.aborted) {
          setWorkflows(definitions);
          setRuns(history.items);
        }
      } catch (loadError) {
        if (!abort.signal.aborted) {
          setError(errorText(loadError));
        }
      } finally {
        if (!abort.signal.aborted) {
          setLoading(false);
        }
      }
    })();

    return () => abort.abort();
  }, [enabled, persistControls]);

  useEffect(() => {
    if (!enabled || !session) {
      return;
    }
    let cancelled = false;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      try {
        for (const control of controls.current) {
          try {
            const receipt = await client.control(control.id, abort.signal);
            if (cancelled) {
              return;
            }
            if (
              (control.kind === 'start' || control.kind === 'restart') &&
              current.current !== receipt.runId &&
              stoppedRunAcceptsUpdate(stoppedRunIds.current, receipt.runId)
            ) {
              select(receipt.runId);
            }
            if (receipt.delivery === 'RETURNED') {
              if (control.kind === 'stop') {
                stoppedRunIds.current.add(receipt.runId);
                beginRead(readGenerations.current, receipt.runId);
              }
              removeControl(control.id);
              setUncertain(false);
            } else if (receipt.delivery === 'UNCONFIRMED') {
              setUncertain(true);
              setError('请求执行结果未确认。请查看原运行，勿重复提交。');
            }
          } catch (controlError) {
            if (!(controlError instanceof ApiError && controlError.code === 'NOT_FOUND')) {
              throw controlError;
            }
          }
        }

        if (current.current) {
          const id = current.current;
          const generation = beginRead(readGenerations.current, id);
          const next = await client.view(id, abort.signal);
          if (
            !cancelled &&
            current.current === id &&
            isCurrentRead(readGenerations.current, id, generation)
          ) {
            setView(next);
          }
        }
      } catch (pollError) {
        if (!cancelled) {
          setError(errorText(pollError));
        }
      } finally {
        if (!cancelled) {
          timer = setTimeout(poll, 1500);
        }
      }
    };

    void poll();
    return () => {
      cancelled = true;
      abort.abort();
      clearTimeout(timer);
    };
  }, [enabled, session, select, removeControl]);

  const mutate = useCallback(
    async (
      kind: ControlKind,
      execute: (controlId: string) => Promise<unknown>,
    ) => {
      if (!canDispatch(controls.current, locks.current, kind)) {
        throw new Error('上次请求尚未确认');
      }

      locks.current.add(kind);
      const id = createUuidV4();
      const targetRunId = current.current ?? undefined;
      addControl({ id, kind, runId: targetRunId });
      setError('');

      try {
        const response = object(await execute(id));
        const responseRunId = string(response.runId);
        const lifecycle = response.lifecycle === undefined ? undefined : string(response.lifecycle);

        if (kind === 'stop') {
          stoppedRunIds.current.add(responseRunId);
          beginRead(readGenerations.current, responseRunId);
        }
        if (
          (kind === 'start' || kind === 'restart') &&
          stoppedRunAcceptsUpdate(stoppedRunIds.current, responseRunId)
        ) {
          select(responseRunId);
        }

        removeControl(id);
        setUncertain(false);
        void refreshReadModel(responseRunId);

        if (kind === 'stop' && lifecycle === 'STOPPED' && alive.current) {
          setError('');
        }
      } catch (writeError) {
        if (alive.current) {
          if (isDefinitelyRejected(writeError)) {
            removeControl(id);
            setUncertain(false);
            setError(errorText(writeError));
          } else {
            setUncertain(true);
            setError(`${errorText(writeError)} 请求编号已保留，可查询原请求。`);
          }
        }
        throw writeError;
      } finally {
        locks.current.delete(kind);
      }
    },
    [addControl, refreshReadModel, removeControl, select],
  );

  const nonStopPending = pendingControls.some((control) => control.kind !== 'stop');
  const stopPending = pendingControls.some((control) => control.kind === 'stop');

  return {
    session,
    workflows,
    runs,
    view,
    runId,
    error,
    loading,
    pendingControls,
    uncertain,
    nonStopPending,
    stopPending,
    select,
    start: (key: string, inputs: JsonObject) =>
      mutate('start', (id) => client.start(id, key, inputs)),
    stop: () => {
      if (!runId) {
        throw new Error('未选择运行');
      }
      return mutate('stop', (id) => client.stop(runId, id));
    },
    restart: (inputs: JsonObject) => {
      if (!runId || view?.lifecycle !== 'STOPPED') {
        throw new Error('请先明确停止原运行');
      }
      return mutate('restart', (id) => client.restart(runId, id, inputs));
    },
    action: (
      nodeId: string,
      interactionId: string,
      name: string,
      inputs: JsonObject,
    ) => {
      if (!runId) {
        throw new Error('未选择运行');
      }
      return mutate('action', (id) =>
        client.action(runId, nodeId, id, interactionId, name, inputs),
      );
    },
    refresh: async () => {
      if (runId) {
        await refreshReadModel(runId);
      }
    },
  };
}
