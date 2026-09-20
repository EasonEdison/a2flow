// Incremental SSE framing; no buffered response.text() and no reconnect/replay.
export async function readChatStream(response, onEvent) {
  if (!response.body) throw new Error('CHAT_STREAM_MISSING');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', sequence = 0, messageId, terminal = false;
  const consume = () => {
    let match;
    while ((match = /\r?\n\r?\n/.exec(buffer))) {
      const block = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      const data = block.split(/\r?\n/).filter(line => line.startsWith('data:'))
        .map(line => line.slice(5).replace(/^ /, '')).join('\n');
      if (!data) continue;
      const event = JSON.parse(data);
      if (!Number.isSafeInteger(event.sequence) || typeof event.messageId !== 'string'
          || typeof event.inputMessageId !== 'string') throw new Error('CHAT_STREAM_INVALID');
      if (messageId && messageId !== event.messageId) throw new Error('CHAT_STREAM_ID_CHANGED');
      messageId = event.messageId;
      if (event.sequence <= sequence) continue;
      if (event.sequence !== sequence + 1 || terminal) throw new Error('CHAT_STREAM_SEQUENCE');
      sequence = event.sequence;
      terminal = event.type === 'done' || event.type === 'error';
      onEvent(event);
    }
    if (buffer.length > 2_000_000) throw new Error('CHAT_STREAM_FRAME_TOO_LARGE');
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      consume();
      if (done) break;
    }
    if (!terminal) throw new Error('CHAT_STREAM_DISCONNECTED');
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
