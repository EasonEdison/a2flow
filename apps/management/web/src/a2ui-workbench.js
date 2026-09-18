const SUPPORTED_COMPONENTS = new Set(['Column', 'Text', 'ChoicePicker', 'Button']);
const FORBIDDEN_KEYS = new Set(['__proto__', 'prototype', 'constructor', 'html', 'script', 'src', 'href', 'url', 'uri']);
const MAX_COMPONENTS = 128;
const MAX_DEPTH = 16;
const MAX_JSON_SIZE = 100000;
const MAX_CHILD_REFS = 256;
const MAX_RENDER_VISITS = 512;

function record(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function issue(code, path, message, componentId, samplePath) {
  return { code, path, message, ...(componentId ? { componentId } : {}), ...(samplePath ? { samplePath } : {}) };
}

function pointerToken(value) {
  return String(value).replace(/~/g, '~0').replace(/\//g, '~1');
}

function validBinding(value) {
  return record(value) && typeof value.path === 'string' && value.path.startsWith('/') && value.path.length <= 256;
}

function pointer(value, path) {
  if (typeof path !== 'string' || !path.startsWith('/') || path.length > 256) return { ok: false };
  let current = value;
  for (const token of path.slice(1).split('/').map((part) => part.replace(/~1/g, '/').replace(/~0/g, '~'))) {
    if (!record(current) && !Array.isArray(current)) return { ok: false };
    if (!Object.hasOwn(current, token)) return { ok: false };
    current = current[token];
  }
  return { ok: true, value: current };
}

function unsafe(value, depth = 0) {
  if (depth > MAX_DEPTH) return true;
  if (Array.isArray(value)) return value.some((item) => unsafe(item, depth + 1));
  if (!record(value)) return false;
  return Object.entries(value).some(([key, child]) => FORBIDDEN_KEYS.has(key) || unsafe(child, depth + 1));
}

function componentsOf(surface) {
  return record(surface) && Array.isArray(surface.components) ? surface.components : null;
}

export function analyzeSurface(surface) {
  const issues = [];
  const components = componentsOf(surface);
  if (!components) return { nodes: [], issues: [issue('INVALID_COMPONENTS', '/components', 'components 必须是数组。')] };
  if (components.length > MAX_COMPONENTS) issues.push(issue('COMPONENT_LIMIT', '/components', `组件不得超过 ${MAX_COMPONENTS} 个。`));
  const firstById = new Map();
  const nodes = components.map((component, index) => {
    const path = `/components/${index}`;
    if (!record(component)) {
      issues.push(issue('MALFORMED_COMPONENT', path, '组件不是对象。'));
      return { index, id: null, component: null, children: [], supported: false, path };
    }
    const id = typeof component.id === 'string' && component.id ? component.id : null;
    const type = typeof component.component === 'string' ? component.component : null;
    if (!id) issues.push(issue('INVALID_COMPONENT_ID', `${path}/id`, '组件 ID 必须是非空字符串。'));
    else if (firstById.has(id)) issues.push(issue('DUPLICATE_COMPONENT_ID', `${path}/id`, `组件 ID ${id} 重复。`, id));
    else firstById.set(id, index);
    if (!SUPPORTED_COMPONENTS.has(type)) issues.push(issue('UNSUPPORTED_COMPONENT', `${path}/component`, `不支持的组件类型 ${String(type)}。`, id));
    const children = Array.isArray(component.children) ? component.children.slice() : [];
    if (type === 'Column' && !Array.isArray(component.children)) issues.push(issue('INVALID_CHILDREN', `${path}/children`, 'Column children 必须是数组。', id));
    if (children.length > MAX_CHILD_REFS) issues.push(issue('CHILD_REF_LIMIT', `${path}/children`, `单个组件的 children 不得超过 ${MAX_CHILD_REFS} 项。`, id));
    if (type === 'Text' && !validBinding(component.text)) issues.push(issue('INVALID_TEXT_BINDING', `${path}/text`, 'Text text 必须是包含有效 path 的对象。', id));
    if (type === 'ChoicePicker') {
      if (!validBinding(component.options)) issues.push(issue('INVALID_OPTIONS_BINDING', `${path}/options`, 'ChoicePicker options 必须是包含有效 path 的对象。', id));
      if (!validBinding(component.value)) issues.push(issue('INVALID_VALUE_BINDING', `${path}/value`, 'ChoicePicker value 必须是包含有效 path 的对象。', id));
    }
    if (type === 'Button') {
      const event = record(component.action) && record(component.action.event) ? component.action.event : null;
      const context = event && record(event.context) ? event.context : null;
      if (!event || typeof event.name !== 'string' || !context || Object.keys(context).length > 64
        || Object.values(context).some((binding) => !record(binding)
          || !((Object.keys(binding).length === 1 && Object.hasOwn(binding, 'literal'))
            || (Object.keys(binding).length === 1 && validBinding(binding))))) {
        issues.push(issue('INVALID_BUTTON_ACTION', `${path}/action`, 'Button action.event 必须包含 name 与有界的 literal/path context。', id));
      }
    }
    return { index, id, component: type, children, supported: SUPPORTED_COMPONENTS.has(type), path };
  });
  for (const node of nodes) {
    node.children.forEach((childId, childIndex) => {
      if (typeof childId !== 'string' || !firstById.has(childId)) issues.push(issue('DANGLING_COMPONENT_REF', `${node.path}/children/${childIndex}`, `找不到子组件 ${String(childId)}。`, node.id));
    });
  }
  const rootId = record(surface) ? surface.rootId : undefined;
  if (typeof rootId !== 'string' || !firstById.has(rootId)) issues.push(issue('INVALID_ROOT_ID', '/rootId', 'rootId 未指向有效组件。'));
  const visiting = new Set();
  const visited = new Set();
  function visit(id, depth) {
    if (depth > MAX_DEPTH) {
      issues.push(issue('COMPONENT_DEPTH', '/rootId', `组件层级不得超过 ${MAX_DEPTH}。`, id));
      return;
    }
    if (visiting.has(id)) {
      issues.push(issue('COMPONENT_CYCLE', '/components', `组件引用形成循环：${id}。`, id));
      return;
    }
    if (visited.has(id)) return;
    const index = firstById.get(id);
    if (index === undefined) return;
    visiting.add(id);
    for (const child of nodes[index].children) if (typeof child === 'string') visit(child, depth + 1);
    visiting.delete(id);
    visited.add(id);
  }
  if (typeof rootId === 'string') visit(rootId, 0);
  let renderVisits = 0;
  function countRenderVisits(id, depth) {
    if (depth > MAX_DEPTH || renderVisits > MAX_RENDER_VISITS) return;
    const index = firstById.get(id);
    if (index === undefined) return;
    renderVisits += 1;
    for (const child of nodes[index].children) {
      if (typeof child === 'string') countRenderVisits(child, depth + 1);
      if (renderVisits > MAX_RENDER_VISITS) break;
    }
  }
  if (typeof rootId === 'string') countRenderVisits(rootId, 0);
  if (renderVisits > MAX_RENDER_VISITS) issues.push(issue('RENDER_VISIT_LIMIT', '/rootId', `预览展开不得超过 ${MAX_RENDER_VISITS} 个组件实例。`, typeof rootId === 'string' ? rootId : undefined));
  for (const node of nodes) if (node.id && !visited.has(node.id)) issues.push(issue('UNREACHABLE_COMPONENT', node.path, `组件 ${node.id} 不在 rootId 层级中。`, node.id));
  return { nodes, issues };
}

function replaceComponents(surface, components) {
  return { ...surface, components };
}

export function updateComponentProperty(surface, index, path, value) {
  const components = componentsOf(surface);
  if (!components || !record(components[index]) || !Array.isArray(path) || !path.length || path[0] === 'id' || path.some((key) => typeof key !== 'string' || FORBIDDEN_KEYS.has(key))) return surface;
  let ancestor = components[index];
  for (let offset = 0; offset < path.length - 1; offset += 1) {
    if (!record(ancestor) || !Object.hasOwn(ancestor, path[offset]) || !record(ancestor[path[offset]])) return surface;
    ancestor = ancestor[path[offset]];
  }
  const update = (current, offset) => {
    const key = path[offset];
    return { ...current, [key]: offset === path.length - 1 ? value : update(current[key], offset + 1) };
  };
  const next = components.slice();
  next[index] = update(next[index], 0);
  return replaceComponents(surface, next);
}

export function moveComponent(surface, index, direction) {
  const components = componentsOf(surface);
  const target = index + direction;
  if (!components || !Number.isInteger(index) || ![-1, 1].includes(direction) || target < 0 || target >= components.length) return surface;
  const next = components.slice();
  [next[index], next[target]] = [next[target], next[index]];
  return replaceComponents(surface, next);
}

export function removeComponent(surface, index) {
  const components = componentsOf(surface);
  if (!components || !Number.isInteger(index) || index < 0 || index >= components.length) return surface;
  return replaceComponents(surface, components.filter((_, rowIndex) => rowIndex !== index));
}

export function addComponent(surface, component) {
  const components = componentsOf(surface);
  if (!components || !SUPPORTED_COMPONENTS.has(component) || components.length >= MAX_COMPONENTS) return surface;
  const ids = new Set(components.filter(record).map((item) => item.id));
  let suffix = components.length + 1;
  while (ids.has(`${component.toLowerCase()}-${suffix}`)) suffix += 1;
  const id = `${component.toLowerCase()}-${suffix}`;
  const templates = {
    Column: { id, component, children: [] },
    Text: { id, component, text: { path: '/' } },
    ChoicePicker: { id, component, options: { path: '/' }, value: { path: '/' }, variant: 'mutuallyExclusive' },
    Button: { id, component, label: 'Button', action: { event: { name: '', context: {} } } },
  };
  return replaceComponents(surface, [...components, templates[component]]);
}

function expectedType(schema) {
  return record(schema) && typeof schema.type === 'string' ? schema.type : null;
}

function matchesType(value, type) {
  if (type === 'object') return record(value);
  if (type === 'array') return Array.isArray(value);
  if (type === 'string') return typeof value === 'string';
  if (type === 'number') return typeof value === 'number' && Number.isFinite(value);
  if (type === 'integer') return Number.isInteger(value);
  if (type === 'boolean') return typeof value === 'boolean';
  if (type === 'null') return value === null;
  return true;
}

function bindings(component) {
  if (!record(component)) return [];
  if (component.component === 'Text') return [['text', component.text]];
  if (component.component === 'ChoicePicker') return [['options', component.options], ['value', component.value]];
  if (component.component === 'Button' && record(component.action) && record(component.action.event) && record(component.action.event.context)) return Object.entries(component.action.event.context);
  return [];
}

export function validateSample(surface, sample) {
  const issues = [];
  if (!record(sample)) return { valid: false, issues: [issue('INVALID_SAMPLE', '/', '示例输入必须是 JSON 对象。', undefined, '/')] };
  if (unsafe(sample) || JSON.stringify(sample).length > MAX_JSON_SIZE) return { valid: false, issues: [issue('UNSAFE_SAMPLE', '/', '示例输入包含不安全键、过深或过大。', undefined, '/')] };
  const schema = record(surface) ? surface.inputSchema : null;
  if (record(schema)) {
    const hasNestedSchema = record(schema.properties) && Object.values(schema.properties).some((property) => record(property)
      && (record(property.properties) || Array.isArray(property.required) || Object.hasOwn(property, 'items') || Object.hasOwn(property, 'oneOf') || Object.hasOwn(property, 'anyOf') || Object.hasOwn(property, 'allOf')));
    if (hasNestedSchema || Object.hasOwn(schema, 'oneOf') || Object.hasOwn(schema, 'anyOf') || Object.hasOwn(schema, 'allOf')) {
      issues.push(issue('PARTIAL_SCHEMA_VALIDATION', '/inputSchema', '本地预览仅检查顶层 required/type；嵌套与组合 schema 仍需后端验证。'));
    }
    for (const key of Array.isArray(schema.required) ? schema.required : []) {
      if (typeof key === 'string' && !Object.hasOwn(sample, key)) issues.push(issue('SAMPLE_REQUIRED', '/inputSchema/required', `缺少必填示例值 ${key}。`, undefined, `/${pointerToken(key)}`));
    }
    if (record(schema.properties)) {
      for (const [key, property] of Object.entries(schema.properties)) {
        const token = pointerToken(key);
        if (Object.hasOwn(sample, key) && !matchesType(sample[key], expectedType(property))) issues.push(issue('SAMPLE_TYPE', `/inputSchema/properties/${token}`, `${key} 类型不匹配。`, undefined, `/${token}`));
      }
    }
  }
  for (const component of componentsOf(surface) ?? []) {
    if (!record(component)) continue;
    for (const [, binding] of bindings(component)) {
      if (record(binding) && typeof binding.path === 'string') {
        const resolved = pointer(sample, binding.path);
        if (!resolved.ok) issues.push(issue('BINDING_MISSING', binding.path, `绑定路径 ${binding.path} 没有示例值。`, typeof component.id === 'string' ? component.id : undefined, binding.path));
      }
    }
  }
  return { valid: issues.length === 0, issues };
}

function renderComponent(component, byId, sample, depth, budget) {
  if (depth > MAX_DEPTH || budget.remaining <= 0 || !record(component) || !SUPPORTED_COMPONENTS.has(component.component)) return null;
  budget.remaining -= 1;
  if (component.component === 'Column') return { id: component.id, component: 'Column', children: component.children.map((id) => renderComponent(byId.get(id), byId, sample, depth + 1, budget)).filter(Boolean) };
  if (component.component === 'Text') return { id: component.id, component: 'Text', value: pointer(sample, component.text.path).value };
  if (component.component === 'ChoicePicker') return { id: component.id, component: 'ChoicePicker', options: pointer(sample, component.options.path).value, value: pointer(sample, component.value.path).value };
  return { id: component.id, component: 'Button', label: component.label };
}

export function createPreview(surface, sample) {
  const analysis = analyzeSurface(surface);
  const validation = validateSample(surface, sample);
  if (analysis.issues.length || !validation.valid) return { ok: false, issues: [...analysis.issues, ...validation.issues] };
  const components = componentsOf(surface);
  const byId = new Map(components.map((item) => [item.id, item]));
  return { ok: true, issues: [], root: renderComponent(byId.get(surface.rootId), byId, sample, 0, { remaining: MAX_RENDER_VISITS }) };
}

export function simulateAction(surface, componentId, sample) {
  const component = (componentsOf(surface) ?? []).find((item) => record(item) && item.id === componentId);
  if (!record(component) || component.component !== 'Button' || !record(component.action) || !record(component.action.event)) return null;
  const event = component.action.event;
  if (typeof event.name !== 'string' || !record(event.context) || Object.keys(event.context).length > 64) return null;
  const args = {};
  for (const [key, binding] of Object.entries(event.context)) {
    if (!record(binding)) return null;
    if (Object.keys(binding).length === 1 && Object.hasOwn(binding, 'literal')) args[key] = binding.literal;
    else if (Object.keys(binding).length === 1 && typeof binding.path === 'string') {
      const resolved = pointer(sample, binding.path);
      if (!resolved.ok) return null;
      args[key] = resolved.value;
    } else return null;
  }
  const result = { simulated: true, componentId, name: event.name, arguments: args };
  return JSON.stringify(result).length <= 10000 ? result : null;
}

export const A2UI_COMPONENT_TYPES = Object.freeze([...SUPPORTED_COMPONENTS]);
