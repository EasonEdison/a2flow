const MISSING = Symbol('missing');
const MAX_DEPTH = 8;
const MAX_ENTRIES = 200;
const MAX_SUMMARY_ITEMS = 20;
const MAX_SUMMARY_CHARS = 2400;

function pointer(path, key) {
  return path + '/' + String(key).replaceAll('~', '~0').replaceAll('/', '~1');
}

function typeOf(value) {
  if (value === MISSING) return 'missing';
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  return typeof value;
}

function shownString(value) {
  const base64Like = value.length >= 128 && /^[A-Za-z0-9+/=\r\n]+$/.test(value);
  if (value.length <= 240 && !base64Like) return value;
  return `[string ${value.length} chars${base64Like ? ', base64-like' : ''}; detail omitted]`;
}

function summarize(value, depth = 0, budget = { items: MAX_SUMMARY_ITEMS, chars: MAX_SUMMARY_CHARS }) {
  if (typeof value === 'string') {
    budget.chars -= Math.min(value.length, 240);
    return shownString(value);
  }
  if (value === null || typeof value !== 'object') return value;
  if (depth >= MAX_DEPTH || budget.items <= 0 || budget.chars <= 0) {
    return `[truncated ${Array.isArray(value) ? 'array' : 'object'}; detail omitted]`;
  }
  budget.items -= 1;
  if (Array.isArray(value)) {
    const result = [];
    const length = Math.min(value.length, MAX_SUMMARY_ITEMS);
    for (let index = 0; index < length && budget.items > 0 && budget.chars > 0; index += 1) {
      result.push(summarize(value[index], depth + 1, budget));
    }
    if (length < value.length || budget.items <= 0 || budget.chars <= 0) {
      result.push(`[truncated; ${value.length - result.length} array entries omitted]`);
    }
    return result;
  }
  const result = {};
  const keys = Object.keys(value).sort();
  let used = 0;
  for (const key of keys) {
    if (used >= MAX_SUMMARY_ITEMS || budget.items <= 0 || budget.chars <= 0) break;
    budget.chars -= key.length;
    result[key] = summarize(value[key], depth + 1, budget);
    used += 1;
  }
  if (used < keys.length || budget.items <= 0 || budget.chars <= 0) {
    result['[truncated]'] = `${keys.length - used} object entries omitted`;
  }
  return result;
}

function append(changes, entry) {
  if (changes.length < MAX_ENTRIES) changes.push(entry);
  return changes.length < MAX_ENTRIES;
}

function walk(before, after, path, depth, changes) {
  if (changes.length >= MAX_ENTRIES) return false;
  if (depth >= MAX_DEPTH) {
    if (JSON.stringify(before) !== JSON.stringify(after)) append(changes, {
      path: path || '/', kind: 'truncated',
      before: summarize(before), after: summarize(after),
    });
    return changes.length < MAX_ENTRIES;
  }
  if (before === MISSING) return append(changes, { path: path || '/', kind: 'added', after: summarize(after) });
  if (after === MISSING) return append(changes, { path: path || '/', kind: 'removed', before: summarize(before) });
  const beforeType = typeOf(before);
  const afterType = typeOf(after);
  if (beforeType !== afterType) {
    return append(changes, { path: path || '/', kind: 'type', before: summarize(before), after: summarize(after) });
  }
  if (beforeType === 'array') {
    const length = Math.max(before.length, after.length);
    for (let index = 0; index < length; index += 1) {
      if (!walk(
        index < before.length ? before[index] : MISSING,
        index < after.length ? after[index] : MISSING,
        pointer(path, index), depth + 1, changes,
      )) return false;
    }
    return true;
  }
  if (beforeType === 'object') {
    const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort();
    for (const key of keys) {
      if (!walk(
        Object.hasOwn(before, key) ? before[key] : MISSING,
        Object.hasOwn(after, key) ? after[key] : MISSING,
        pointer(path, key), depth + 1, changes,
      )) return false;
    }
    return true;
  }
  if (!Object.is(before, after)) {
    return append(changes, { path: path || '/', kind: 'changed', before: summarize(before), after: summarize(after) });
  }
  return true;
}

export function diffValues(before, after, path = '') {
  const changes = [];
  const complete = walk(before, after, path, 0, changes);
  if (!complete) changes.push({
    path: path || '/', kind: 'truncated',
    after: `[truncated; remaining differences omitted after ${MAX_ENTRIES} entries]`,
  });
  return changes;
}
