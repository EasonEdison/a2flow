// A pending transport request is not a new user intent. Keep its ID and payload
// until the server has acknowledged it, including across a page reload.
export const pendingChatSendKey = (owner, conversation) => `a2flow:pending-send:v1:${encodeURIComponent(owner)}:${encodeURIComponent(conversation)}`;
export function readPendingChatSend(key, storage = sessionStorage) {
  const raw = storage.getItem(key);
  if (!raw) return null;
  const value = JSON.parse(raw);
  if (!value || typeof value.clientRequestId !== 'string' || !value.clientRequestId
      || typeof value.text !== 'string' || !value.text.trim() || !Array.isArray(value.references)) {
    throw new Error('PENDING_CHAT_SEND_INVALID');
  }
  return value;
}
export function persistPendingChatSend(key, request, storage = sessionStorage) {
  // Do not evict or expire unresolved sends: doing so could create a new intent.
  storage.setItem(key, JSON.stringify(request));
}
export function acknowledgePendingChatSend(key, requestId, storage = sessionStorage) {
  const pending = readPendingChatSend(key, storage);
  if (pending?.clientRequestId === requestId) storage.removeItem(key);
}
