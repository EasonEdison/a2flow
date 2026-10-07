import { AssistantRuntimeProvider, MessagePrimitive, ThreadPrimitive, useExternalStoreRuntime } from '@assistant-ui/react';
import { useMemo } from 'react';
import { toAssistantMessage } from '../assistantChat';
import { workflowMessage } from '../workflowPresentation';
import type { NodeView } from '../presentation';
import { ExecutionPanel } from './AssistantThread';

export function WorkflowExecution({ node }: { node: NodeView }) {
  const message = useMemo(() => workflowMessage(node), [node.id, node.status, node.records, node.output]);
  const runtime = useExternalStoreRuntime({
    messages: [message], convertMessage: toAssistantMessage,
    isRunning: node.status === 'RUNNING', isDisabled: true,
    onNew: async () => { throw new Error('工作流过程为只读视图'); },
  });
  return <AssistantRuntimeProvider runtime={runtime}>
    <ThreadPrimitive.Root className="workflow-execution">
      <ThreadPrimitive.Messages>{() => <MessagePrimitive.Root>
        <ExecutionPanel message={message} />
      </MessagePrimitive.Root>}</ThreadPrimitive.Messages>
    </ThreadPrimitive.Root>
  </AssistantRuntimeProvider>;
}
