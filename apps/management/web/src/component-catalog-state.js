function record(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function inspectPublishedComponentCatalog(detail, expectedKey) {
  if (!record(detail) || !record(detail.definition)) {
    return { ok: false, error: '已发布组件目录缺少 definition。' };
  }
  const { catalogKey, protocolProfileRef, components } = detail.definition;
  if (catalogKey !== expectedKey) {
    return { ok: false, error: '已发布组件目录标识与 Application 引用不一致。' };
  }
  if (typeof protocolProfileRef !== 'string' || !protocolProfileRef || !Array.isArray(components)
    || components.some((name) => typeof name !== 'string' || !name)) {
    return { ok: false, error: '已发布组件目录结构无效。' };
  }
  if (new Set(components).size !== components.length) {
    return { ok: false, error: '已发布组件目录包含重复成员。' };
  }
  return { ok: true, catalogKey, protocolProfileRef, components };
}
