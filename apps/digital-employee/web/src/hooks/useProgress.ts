import { useEffect, useState } from 'react';

import { client, type ProgressClient } from '../api/client';
import { parseRecord } from '../api/contracts';
import { recordLine } from '../api/adapter';
import type { RecordLine } from '../presentation';

type ProgressState = {
  runId: string | null;
  records: Record<string, RecordLine[]>;
  error: string;
  historyStatus: 'loading' | 'ready' | 'incomplete';
};

/** Two sequential Skills: max two observers; committed history always precedes SSE. */
export function useProgress(runId: string | null, transport: ProgressClient = client, live = true) {
  const [state, setState] = useState<ProgressState>({ runId: null, records: {}, error: '', historyStatus: 'loading' });

  useEffect(() => {
    if (!runId) return;
    const abort = new AbortController();
    let alive = true;
    let poll: ReturnType<typeof setTimeout>;
    const streams = new Map<string, EventSource>();
    const cursors = new Map<string, string>();
    const completed = new Set<string>();
    const reconnecting = new Set<string>();
    const retryTimers = new Set<ReturnType<typeof setTimeout>>();
    const seen = new Set<string>();
    let captureIncomplete = false;
    let hydrating = true;
    let bufferedRecords: Record<string, RecordLine[]> = {};
    const pendingStreams = new Map<string, string>();
    setState({ runId, records: {}, error: '', historyStatus: 'loading' });

    const unavailable = (permanent = false) => {
      captureIncomplete ||= permanent;
      if (!alive) return;
      if (hydrating) return;
      setState(previous => ({
        runId,
        records: previous.runId === runId ? previous.records : {},
        historyStatus: permanent ? 'incomplete' : previous.historyStatus,
        error: '执行过程未完整加载，以下仅为已加载记录，调用次数不是总数；节点状态以服务端为准。',
      }));
    };

    const addRecord = (nodeId: string, executionId: string, value: unknown) => {
      const record = parseRecord(value);
      const key = executionId + ':' + record.seq;
      if (seen.has(key)) return;
      seen.add(key);
      cursors.set(executionId, key);
      if (!alive) return;
      const records = [...(bufferedRecords[nodeId] ?? []), recordLine(executionId, record)];
      if (records.length > 2000) unavailable(true);
      bufferedRecords = { ...bufferedRecords, [nodeId]: records.slice(-2000) };
      if (!hydrating) setState(previous => ({ ...previous, runId, records: bufferedRecords }));
    };

    const connect = (nodeId: string, executionId: string) => {
      if (!alive || !live || hydrating || streams.size >= 2 || completed.has(executionId) || streams.has(executionId)) return;
      reconnecting.delete(executionId);
      const source = new EventSource(
        transport.streamUrl(runId, nodeId, executionId, cursors.get(executionId)),
        { withCredentials: true },
      );
      streams.set(executionId, source);
      source.addEventListener('progress', event => {
        try {
          addRecord(nodeId, executionId, JSON.parse((event as MessageEvent).data));
        } catch {
          source.close();
          streams.delete(executionId);
          unavailable();
        }
      });
      source.addEventListener('capture_end', () => {
        completed.add(executionId);
        source.close();
        streams.delete(executionId);
        if (!captureIncomplete && reconnecting.size === 0) {
          setState(previous => previous.runId === runId && previous.error
            ? { ...previous, error: '' } : previous);
        }
      });
      source.addEventListener('capture', event => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          if (data.capture?.incomplete || data.capture?.observation_outcome === 'UNAVAILABLE') {
            unavailable(true);
          }
        } catch {
          unavailable();
        }
      });
      source.addEventListener('error', () => {
        source.close();
        streams.delete(executionId);
        if (!alive) return;
        unavailable();
        if (reconnecting.has(executionId)) return;
        reconnecting.add(executionId);
        const timer = setTimeout(() => {
          retryTimers.delete(timer);
          connect(nodeId, executionId);
        }, 3000);
        retryTimers.add(timer);
      });
    };

    const discover = async () => {
      let historyComplete = false;
      try {
        let cursor: string | undefined;
        for (let page = 0; page < 20; page++) {
          const catalog = await transport.catalog(runId, cursor, abort.signal);
          for (const segment of catalog.segments) {
            const executionId = segment.execution_id;
            if (seen.has('segment:' + executionId)) continue;
            let after: string | undefined;
            let sealed = segment.sealed;
            let segmentComplete = false;
            for (let historyPage = 0; historyPage < 20; historyPage++) {
              const history = await transport.history(
                runId, segment.node_id, executionId, after, abort.signal,
              );
              for (const record of history.records) addRecord(segment.node_id, executionId, record);
              after = history.nextCursor;
              cursors.set(executionId, after);
              sealed = history.capture.sealed;
              if (history.capture.incomplete || history.capture.observation_outcome === 'UNAVAILABLE') unavailable(true);
              if (!history.hasMore) { segmentComplete = true; break; }
              if (!after) throw new Error('Missing history cursor');
            }
            if (!segmentComplete) throw new Error('History page limit reached');
            seen.add('segment:' + executionId);
            if (sealed) completed.add(executionId);
            else pendingStreams.set(executionId, segment.node_id);
          }
          if (!catalog.hasMore) { historyComplete = true; break; }
          cursor = catalog.nextCursor;
          if (!cursor) throw new Error('Missing catalog cursor');
        }
        if (!historyComplete) throw new Error('Catalog page limit reached');
      } catch {
        if (alive && !hydrating) unavailable();
      } finally {
        if (!alive) return;
        if (hydrating) {
          setState({
            runId, records: historyComplete ? bufferedRecords : {},
            historyStatus: historyComplete && !captureIncomplete ? 'ready' : 'incomplete',
            error: historyComplete && !captureIncomplete ? ''
              : '执行过程未完整加载，调用次数暂不能作为总数；节点状态以服务端为准。',
          });
          // A failed initial read stays buffered until its remaining pages arrive.
          hydrating = !historyComplete;
        }
        if (!hydrating) for (const [executionId, nodeId] of pendingStreams) {
          if (completed.has(executionId)) pendingStreams.delete(executionId);
          else connect(nodeId, executionId);
        }
        if (live) poll = setTimeout(discover, 2000);
      }
    };

    void discover();
    return () => {
      alive = false;
      abort.abort();
      clearTimeout(poll);
      for (const source of streams.values()) source.close();
      for (const timer of retryTimers) clearTimeout(timer);
    };
  }, [runId, transport, live]);

  return state.runId === runId ? state : { runId, records: {}, error: '', historyStatus: 'loading' as const };
}
