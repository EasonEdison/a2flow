export function upsertConversation(items, conversation) {
  return [conversation, ...items.filter((item) => item.id !== conversation.id)];
}

export function appendMessage(items, message) {
  return [...items, message];
}

export function markNotificationRead(items, id) {
  return items.map((item) => (item.id === id ? { ...item, read: true } : item));
}

export function unreadCount(items) {
  return items.filter((item) => !item.read).length;
}

export function toggleSchedule(items, id, enabled) {
  return items.map((item) => (item.id === id ? { ...item, enabled } : item));
}

export function removeSchedule(items, id) {
  return items.filter((item) => item.id !== id);
}
