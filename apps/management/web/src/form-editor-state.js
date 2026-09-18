const UNSAFE_KEYS = new Set(['__proto__', 'prototype', 'constructor']);

function safePath(path) {
  if (!Array.isArray(path) || path.some((key) => typeof key !== 'string' || UNSAFE_KEYS.has(key))) {
    throw new Error('UNSAFE_PATH');
  }
}

function objectAt(document, path) {
  return path.reduce((value, key) => value?.[key], document);
}

function editableContainer(value) {
  return isEditableRecord(value) || Array.isArray(value);
}

function validContainerKey(value, key) {
  return !Array.isArray(value) || /^(0|[1-9]\d*)$/.test(key);
}

const JSON_FIELD_LABELS = new Map([
  ['modelArgumentSchema', 'Model argument schema'],
  ['resolvedInputSchema', 'Resolved input schema'],
  ['outputSchema', 'Output schema'],
  ['resultInterpretationPolicies', 'Result interpretation policies'],
  ['definition.surfaceTemplate', 'Surface template'],
  ['definition.surfaceTemplate.inputSchema', 'Parameter schema'],
]);

function jsonFieldLabel(path) {
  const known = JSON_FIELD_LABELS.get(pathKey(path));
  if (known) return known;
  return path.length >= 5 && path[0] === 'definition' && path[1] === 'surfaceTemplate' && path[2] === 'components' && path.at(-1) === 'children'
    ? 'Children IDs'
    : path.join('.');
}

function pathKey(path) {
  safePath(path);
  return path.join('.');
}

function pathFromKey(key) {
  return key.split('.');
}

function valuesEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function createPendingFieldState() {
  return {};
}

export function editPendingField(pending, path, text, expected, baseValue) {
  const key = pathKey(path);
  const parsed = expected ? parseJsonField(text, expected) : (() => {
    try {
      JSON.parse(text);
      return { ok: true };
    } catch (error) {
      return { ok: false, error: error.message };
    }
  })();
  return {
    ...pending,
    [key]: {
      path: [...path],
      text,
      expected: expected ?? pending[key]?.expected ?? null,
      error: parsed.ok ? null : parsed.error,
      conflict: pending[key]?.conflict ?? false,
      hasBase: Object.hasOwn(pending, key) ? pending[key].hasBase : arguments.length >= 5,
      baseValue: Object.hasOwn(pending, key) ? pending[key].baseValue : baseValue,
    },
  };
}

export function pendingFieldConflict(pending, path) {
  for (const entry of Object.values(pending)) {
    if (samePath(entry.path, path)) continue;
    if (pathContains(entry.path, path) || pathContains(path, entry.path)) {
      return `${jsonFieldLabel(entry.path)} 存在尚未应用的文本，请先应用或丢弃。`;
    }
  }
  return null;
}

export function applyPendingField(document, pending, path, expected) {
  const key = pathKey(path);
  const entry = pending[key];
  if (!entry) return { applied: false, document, pending };
  const parsed = parseJsonField(entry.text, expected);
  if (!parsed.ok) return { applied: false, document, pending: editPendingField(pending, path, entry.text, expected, entry.baseValue) };
  const currentValue = objectAt(document, path);
  if ((entry.hasBase && !valuesEqual(currentValue, entry.baseValue)) || !inspectPathEditability(document, path).editable || pendingFieldConflict(pending, path)) {
    return {
      applied: false,
      document,
      pending: { ...pending, [key]: { ...entry, conflict: entry.hasBase && !valuesEqual(currentValue, entry.baseValue) } },
    };
  }
  const nextDocument = updatePath(document, path, parsed.value);
  if (nextDocument === document) return { applied: false, document, pending };
  const nextPending = { ...pending };
  delete nextPending[key];
  return { applied: true, document: nextDocument, pending: nextPending };
}

export function discardPendingField(document, pending, path) {
  const nextPending = { ...pending };
  delete nextPending[pathKey(path)];
  return { document, pending: nextPending };
}

export function reconcilePendingFields(pending, document) {
  return Object.fromEntries(Object.entries(pending).map(([key, entry]) => {
    const path = pathFromKey(key);
    return [key, {
      ...entry,
      conflict: entry.hasBase ? !valuesEqual(objectAt(document, path), entry.baseValue) : entry.conflict,
    }];
  }));
}

export function isEditableRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}


export function inspectPathEditability(document, path) {
  safePath(path);
  let value = document;
  for (let index = 0; index < path.length - 1; index += 1) {
    if (!editableContainer(value)) {
      return { editable: false, blockedPath: path.slice(0, index) };
    }
    const key = path[index];
    if (!validContainerKey(value, key)) return { editable: false, blockedPath: path.slice(0, index) };
    if (!Object.hasOwn(value, key)) return { editable: true };
    value = value[key];
    if (!editableContainer(value)) {
      return { editable: false, blockedPath: path.slice(0, index + 1) };
    }
  }
  return editableContainer(value) && validContainerKey(value, path.at(-1)) ? { editable: true } : { editable: false, blockedPath: path.slice(0, -1) };
}

const APPLICATION_JSON_FIELDS = [
  { path: ['definition', 'surfaceTemplate'], label: 'Surface template' },
  { path: ['definition', 'surfaceTemplate', 'inputSchema'], label: 'Parameter schema' },
];

function samePath(left, right) {
  return left.length === right.length && left.every((key, index) => key === right[index]);
}

function pathContains(parent, child) {
  return parent.length < child.length && parent.every((key, index) => key === child[index]);
}

export function jsonFieldConflict(document, path) {
  safePath(path);
  for (const field of APPLICATION_JSON_FIELDS) {
    if (samePath(field.path, path)) continue;
    if ((pathContains(field.path, path) || pathContains(path, field.path))
      && typeof objectAt(document, field.path) === 'string') {
      return `${field.label} 存在尚未应用的文本，请先在该字段修正并应用。`;
    }
  }
  return null;
}

export function inspectDraftText(text) {
  try {
    const document = JSON.parse(text);
    if (document === null || Array.isArray(document) || typeof document !== 'object') {
      return { ok: false, text, error: '草稿根节点必须是 JSON 对象。' };
    }
    return { ok: true, text, document };
  } catch (error) {
    return { ok: false, text, error: `JSON 语法错误：${error.message}` };
  }
}

export function hasPendingJsonField(document) {
  return typeof document?.modelArgumentSchema === 'string'
    || typeof document?.resolvedInputSchema === 'string'
    || typeof document?.outputSchema === 'string'
    || typeof document?.resultInterpretationPolicies === 'string'
    || typeof document?.definition?.surfaceTemplate === 'string'
    || typeof document?.definition?.surfaceTemplate?.inputSchema === 'string';
}

export function parseJsonField(text, expected) {
  try {
    const value = JSON.parse(text);
    if (value === null || typeof value !== 'object' || (expected === 'array') !== Array.isArray(value)) {
      return { ok: false, text, error: `必须是 JSON ${expected === 'array' ? '数组' : '对象'}。` };
    }
    return { ok: true, text, value };
  } catch (error) {
    return { ok: false, text, error: error.message };
  }
}

export function updatePath(document, path, value) {
  safePath(path);
  if (!path.length) return value;
  const editability = inspectPathEditability(document, path);
  if (!editability.editable || jsonFieldConflict(document, path)) return document;
  const [key, ...rest] = path;
  const source = isEditableRecord(document) ? document : {};
  return { ...source, [key]: updatePathUnchecked(source[key], rest, value) };
}

function updatePathUnchecked(document, path, value) {
  if (!path.length) return value;
  const [key, ...rest] = path;
  if (Array.isArray(document)) {
    const source = document.slice();
    source[Number(key)] = updatePathUnchecked(source[Number(key)], rest, value);
    return source;
  }
  const source = isEditableRecord(document) ? document : {};
  return { ...source, [key]: updatePathUnchecked(source[key], rest, value) };
}

export function updateRow(document, path, index, field, value) {
  safePath([...path, field]);
  const rows = objectAt(document, path);
  if (!Array.isArray(rows) || !isEditableRecord(rows[index])) return document;
  const next = rows.slice();
  next[index] = { ...next[index], [field]: value };
  return updatePath(document, path, next);
}

export function appendRow(document, path, row) {
  safePath(path);
  const rows = objectAt(document, path);
  return updatePath(document, path, [...(Array.isArray(rows) ? rows : []), row]);
}

export function removeRow(document, path, index) {
  safePath(path);
  const rows = objectAt(document, path);
  if (!Array.isArray(rows)) return document;
  return updatePath(document, path, rows.filter((_, rowIndex) => rowIndex !== index));
}

export function moveRow(document, path, index, direction) {
  safePath(path);
  const rows = objectAt(document, path);
  const target = index + direction;
  if (!Array.isArray(rows) || target < 0 || target >= rows.length) return document;
  const next = rows.slice();
  [next[index], next[target]] = [next[target], next[index]];
  return updatePath(document, path, next);
}

export function skillFrontmatterMismatch(document) {
  const text = document?.skillMd;
  const metadata = document?.metadata;
  if (typeof text !== 'string' || !metadata || typeof metadata !== 'object') return '无法比较 metadata 与 SKILL.md frontmatter。';
  const match = /^---\n([\s\S]*?)\n---\n/.exec(text);
  if (!match) return 'SKILL.md 需要以仅包含 name 和 description 的 frontmatter 开头。';
  const values = {};
  for (const line of match[1].split('\n')) {
    const separator = line.indexOf(':');
    if (separator < 1) return 'SKILL.md frontmatter 格式无效，请在 JSON 模式修正。';
    const key = line.slice(0, separator);
    if (!['name', 'description'].includes(key) || Object.hasOwn(values, key)) {
      return 'SKILL.md frontmatter 包含不受支持或重复的字段，请在 JSON 模式修正。';
    }
    values[key] = line.slice(separator + 1).trim();
  }
  if (!Object.hasOwn(values, 'name') || !Object.hasOwn(values, 'description')) {
    return 'SKILL.md frontmatter 必须包含 name 和 description。';
  }
  return values.name === metadata.name && values.description === metadata.description
    ? null
    : 'metadata 与 SKILL.md frontmatter 不一致；请明确编辑两处后再验证。';
}

export function workflowTopologyWarning(document) {
  return document?.topology === 'SEQUENTIAL'
    ? null
    : `${String(document?.topology ?? '未知')} 拓扑可保留草稿，但当前后端无法发布；不会自动转换为 SEQUENTIAL。`;
}
