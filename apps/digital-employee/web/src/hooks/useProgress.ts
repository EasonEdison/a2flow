import { useEffect, useState } from 'react';

import { client, type ProgressClient } from '../api/client';
import { parseRecord } from '../api/contracts';
import { recordLine } from '../api/adapter';
import type { RecordLine } from '../presentation';

type ProgressState = {
  runId: string | null;
  records: Record<string, RecordLine[]>;
  error: string;
};

/** Two sequential Skills: max two observers; committed history always precedes SSE. */
export function useProgress(runId: string | null, transport: ProgressClient = client) {
  const [state, setState] = useState<ProgressState>({ runId: null, records: {}, error: '' });

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

    const unavailable = () => {
      if (!alive) return;
      setState(previous => ({
        runId,
        records: previous.runId === runId ? previous.records : {},
        error: '部分过程记录暂不可用，节点状态仍以服务端记录为准。',
      }));
    };

    const addRecord = (nodeId: string, executionId: string, value: unknown) => {
      const record = parseRecord(value);
      const key = executionId + ':' + record.seq;
      if (seen.has(key)) return;
      seen.add(key);
      cursors.set(executionId, key);
      if (!alive) return;
      setState(previous => {
        const records = previous.runId === runId ? previous.records : {};
        return {
          runId,
          error: previous.runId === runId ? previous.error : '',
          records: {
            ...records,
            [nodeId]: [...(records[nodeId] ?? []), recordLine(executionId, record)].slice(-2000),
          },
        };
      });
    };

    const connect = (nodeId: string, executionId: string) => {
      if (!alive || completed.has(executionId) || streams.has(executionId)) return;
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
      });
      source.addEventListener('capture', event => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          if (data.capture?.incomplete || data.capture?.observation_outcome === 'UNAVAILABLE') {
            unavailable();
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
      try {
        let cursor: string | undefined;
        for (let page = 0; page < 20; page++) {
          const catalog = await transport.catalog(runId, cursor, abort.signal);
          for (const segment of catalog.segments) {
            const executionId = segment.execution_id;
            if (seen.has('segment:' + executionId)) continue;
            if (streams.size >= 2) break;
            let after: string | undefined;
            let sealed = segment.sealed;
            for (let historyPage = 0; historyPage < 20; historyPage++) {
              const history = await transport.history(
                runId, segment.node_id, executionId, after, abort.signal,
              );
              for (const record of history.records) addRecord(segment.node_id, executionId, record);
              after = history.nextCursor;
              cursors.set(executionId, after);
              sealed = history.capture.sealed;
              if (history.capture.incomplete) unavailable();
              if (!history.hasMore) break;
            }
            seen.add('segment:' + executionId);
            if (sealed) completed.add(executionId);
            else connect(segment.node_id, executionId);
          }
          if (!catalog.hasMore) break;
          cursor = catalog.nextCursor;
        }
      } catch {
        if (alive) unavailable();
      } finally {
        if (alive) poll = setTimeout(discover, 2000);
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
  }, [runId, transport]);

  return state.runId === runId ? state : { runId, records: {}, error: '' };
}
