import { recoverCodingRunAfterTransportEof } from './runRecovery';

type TestRunStatus = {
  sessionId: string;
  invokeId: string;
  status: 'RUNNING' | 'CANCELLING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  updateTime: number;
};

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function test(description: string, callback: () => Promise<void>) {
  return callback().then(() => console.log(`PASS ${description}`));
}

const status = (value: TestRunStatus['status']): TestRunStatus => ({
  sessionId: 'session-1',
  invokeId: 'invoke-1',
  status: value,
  updateTime: 1,
});

async function main() {
  await test('EOF recovery keeps polling active durable states and returns only on terminal', async () => {
    const responses = [status('RUNNING'), status('CANCELLING'), status('COMPLETED')];
    const observed: string[] = [];
    let queries = 0;
    let waits = 0;

    const outcome = await recoverCodingRunAfterTransportEof<TestRunStatus>({
      queryStatus: async () => responses[queries++],
      waitForNextPoll: async () => {
        waits += 1;
      },
      onStatus: (runStatus) => observed.push(runStatus.status),
    });

    assertEqual(outcome.kind, 'terminal', 'recovery outcome');
    assertEqual(outcome.status?.status, 'COMPLETED', 'durable terminal status');
    assertEqual(queries, 3, 'authoritative status query count');
    assertEqual(waits, 2, 'active-state polling waits');
    assertEqual(observed.join(','), 'RUNNING,CANCELLING,COMPLETED', 'visible status sequence');
  });

  await test('EOF recovery stops when the owning component cancels recovery', async () => {
    const controller = new AbortController();
    let queries = 0;

    const outcome = await recoverCodingRunAfterTransportEof<TestRunStatus>({
      signal: controller.signal,
      queryStatus: async () => {
        queries += 1;
        return status('RUNNING');
      },
      waitForNextPoll: async () => {
        controller.abort();
      },
    });

    assertEqual(outcome.kind, 'cancelled', 'cancelled recovery outcome');
    assertEqual(queries, 1, 'no status query after cancellation');
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
