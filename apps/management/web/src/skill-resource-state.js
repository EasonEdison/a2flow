const MAX_ENTRIES = 127;
const MAX_ENTRY_BYTES = 4 * 1024 * 1024;
const MAX_TOTAL_BYTES = 16 * 1024 * 1024;
const MAX_PATH_LENGTH = 1024;
const MAX_PATH_DEPTH = 32;
const MAX_BASE64_LENGTH = 6 * 1024 * 1024;
export const MANAGEMENT_BODY_LIMIT = 1024 * 1024;
const PATH_PATTERN = /^[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)*$/;
const HANDLE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const DIGEST_PATTERN = /^sha256:[0-9a-f]{64}$/;
const MEDIA_TYPES = new Map([
  ['txt', 'text/plain'], ['md', 'text/markdown'], ['markdown', 'text/markdown'],
  ['json', 'text/plain'], ['yaml', 'text/plain'], ['yml', 'text/plain'], ['csv', 'text/csv'],
  ['png', 'image/png'], ['jpg', 'image/jpeg'], ['jpeg', 'image/jpeg'], ['gif', 'image/gif'], ['webp', 'image/webp'],
]);

function bytesToBase64(bytes) {
  let result = '';
  const step = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += step) {
    result += String.fromCharCode(...bytes.subarray(offset, offset + step));
  }
  return btoa(result);
}

function base64ToBytes(value) {
  if (typeof value !== 'string' || value.length > MAX_BASE64_LENGTH || value.length % 4 === 1 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) {
    throw new Error('INVALID_ENTRY_BYTES');
  }
  const binary = atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function sha256(bytes) {
  if (!globalThis.crypto?.subtle) throw new Error('SECURE_CONTEXT_CRYPTO_UNAVAILABLE');
  let result;
  try { result = await globalThis.crypto.subtle.digest('SHA-256', bytes); }
  catch { throw new Error('SHA256_DIGEST_FAILED'); }
  return `sha256:${[...new Uint8Array(result)].map((value) => value.toString(16).padStart(2, '0')).join('')}`;
}

function descriptorIssue(resource) {
  if (!resource || typeof resource !== 'object' || Array.isArray(resource)) return 'INVALID_ENTRY';
  if (!HANDLE_PATTERN.test(resource.handleId ?? '')) return 'INVALID_HANDLE_ID';
  const path = pathIssue(resource.logicalPath, [], resource);
  if (path) return path;
  if (typeof resource.mediaType !== 'string' || !resource.mediaType || resource.mediaType.length > 128) return 'INVALID_MEDIA_TYPE';
  if (!Number.isInteger(resource.byteSize) || resource.byteSize < 0) return 'INVALID_DECLARED_SIZE';
  if (!DIGEST_PATTERN.test(resource.contentDigest ?? '')) return 'INVALID_DECLARED_DIGEST';
  if (typeof resource.base64 !== 'string') return 'INVALID_ENTRY_BYTES';
  return null;
}

export function resourceIdentity(resource, index = 0) {
  return resource && typeof resource === 'object' && !Array.isArray(resource) && typeof resource.handleId === 'string'
    ? `handle:${resource.handleId}`
    : `malformed:${index}`;
}

export function resourceIdentityIssue(resource, resources) {
  if (!resource || typeof resource !== 'object' || Array.isArray(resource) || typeof resource.handleId !== 'string') return 'INVALID_RESOURCE_IDENTITY';
  return resources.filter((item) => item && typeof item === 'object' && !Array.isArray(item) && item.handleId === resource.handleId).length > 1
    ? 'DUPLICATE_HANDLE_ID'
    : null;
}

export function pathIssue(path, resources = [], current = null) {
  if (typeof path !== 'string' || !path || path.length > MAX_PATH_LENGTH || !PATH_PATTERN.test(path)) return 'INVALID_LOGICAL_PATH';
  const segments = path.split('/');
  if (segments.includes('.') || segments.includes('..')) return 'INVALID_LOGICAL_PATH';
  if (segments.length > MAX_PATH_DEPTH) return 'PATH_DEPTH_LIMIT_EXCEEDED';
  if (path === 'SKILL.md') return 'RESERVED_SKILL_MD';
  if (resources.some((resource) => resource !== current && resource && typeof resource === 'object' && resource.logicalPath === path)) return 'DUPLICATE_LOGICAL_PATH';
  return null;
}

export function inspectResource(resource) {
  const descriptor = descriptorIssue(resource);
  if (descriptor) return { status: 'repair', reason: descriptor };
  let bytes;
  try { bytes = base64ToBytes(resource.base64); }
  catch (error) { return { status: 'repair', reason: error.message }; }
  if (bytes.byteLength !== resource.byteSize) return { status: 'repair', reason: 'DECLARED_SIZE_MISMATCH' };
  if (resource.mediaType.toLowerCase().startsWith('text/')) {
    try {
      const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
      return { status: 'editable', text, pendingDigestCheck: true };
    } catch {
      return { status: 'repair', reason: 'INVALID_TEXT_ENCODING' };
    }
  }
  return { status: 'readonly', reason: 'BINARY_RESOURCE' };
}

export async function inspectResourceVerified(resource) {
  const inspected = inspectResource(resource);
  if (inspected.status === 'repair') return inspected;
  try {
    const bytes = base64ToBytes(resource.base64);
    if (await sha256(bytes) !== resource.contentDigest) return { status: 'repair', reason: 'DECLARED_DIGEST_MISMATCH' };
    return inspected.status === 'readonly' ? { ...inspected, integrity: 'verified' } : { status: 'editable', text: inspected.text };
  } catch (error) {
    return { status: 'repair', reason: error instanceof Error ? error.message : 'SHA256_DIGEST_FAILED' };
  }
}

export function pendingText(resource, text) {
  return { identity: resourceIdentity(resource), base: JSON.stringify(resource), text };
}

export async function applyPendingText(resource, pending) {
  if (!pending || pending.identity !== resourceIdentity(resource) || pending.base !== JSON.stringify(resource)) return { error: 'RESOURCE_CONFLICT' };
  const bytes = new TextEncoder().encode(pending.text);
  if (bytes.byteLength > MAX_ENTRY_BYTES) return { error: 'ENTRY_BYTES_LIMIT_EXCEEDED' };
  return { resource: { ...resource, byteSize: bytes.byteLength, contentDigest: await sha256(bytes), base64: bytesToBase64(bytes) } };
}

export function mediaTypeForPath(path, browserType = '') {
  if (browserType && (browserType.startsWith('text/') || ['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(browserType))) return browserType;
  return MEDIA_TYPES.get(path.split('.').at(-1)?.toLowerCase() ?? '') ?? null;
}

export async function createResource({ handleId, logicalPath, mediaType, bytes, resources = [] }) {
  if (!HANDLE_PATTERN.test(handleId ?? '')) throw new Error('INVALID_HANDLE_ID');
  if (resources.some((resource) => resource?.handleId === handleId)) throw new Error('DUPLICATE_HANDLE_ID');
  const issue = pathIssue(logicalPath, resources);
  if (issue) throw new Error(issue);
  if (typeof mediaType !== 'string' || !mediaType || mediaType.length > 128) throw new Error('INVALID_MEDIA_TYPE');
  if (!(bytes instanceof Uint8Array)) throw new Error('INVALID_ENTRY_BYTES');
  if (bytes.byteLength > MAX_ENTRY_BYTES) throw new Error('ENTRY_BYTES_LIMIT_EXCEEDED');
  const resource = { handleId, logicalPath, mediaType, byteSize: bytes.byteLength, contentDigest: await sha256(bytes), base64: bytesToBase64(bytes) };
  const preflight = checkPackage([...resources, resource]);
  if (preflight.issues.length) throw new Error(preflight.issues[0]);
  return resource;
}

export async function createTextResource({ handleId, logicalPath, mediaType = 'text/plain', text, resources = [] }) {
  return createResource({ handleId, logicalPath, mediaType, bytes: new TextEncoder().encode(text), resources });
}

export function saveBodyIssue(document) {
  return new TextEncoder().encode(JSON.stringify(document)).byteLength > MANAGEMENT_BODY_LIMIT ? 'SAVE_BODY_BUDGET_EXCEEDED' : null;
}

export function checkPackage(resources) {
  const issues = [];
  if (!Array.isArray(resources)) return { issues: ['INVALID_RESOURCES'], entries: 0, totalBytes: 0 };
  if (resources.length > MAX_ENTRIES) issues.push('ENTRY_COUNT_LIMIT_EXCEEDED');
  let totalBytes = 0;
  const paths = new Set();
  const handles = new Set();
  for (const resource of resources) {
    const descriptor = descriptorIssue(resource);
    if (descriptor && !issues.includes(descriptor)) issues.push(descriptor);
    if (resource && typeof resource === 'object') {
      if (typeof resource.logicalPath === 'string') {
        if (paths.has(resource.logicalPath) && !issues.includes('DUPLICATE_LOGICAL_PATH')) issues.push('DUPLICATE_LOGICAL_PATH');
        paths.add(resource.logicalPath);
      }
      if (typeof resource.handleId === 'string') {
        if (handles.has(resource.handleId) && !issues.includes('DUPLICATE_HANDLE_ID')) issues.push('DUPLICATE_HANDLE_ID');
        handles.add(resource.handleId);
      }
      if (Number.isInteger(resource.byteSize) && resource.byteSize >= 0) {
        totalBytes += resource.byteSize;
        if (resource.byteSize > MAX_ENTRY_BYTES && !issues.includes('ENTRY_BYTES_LIMIT_EXCEEDED')) issues.push('ENTRY_BYTES_LIMIT_EXCEEDED');
      }
      if (typeof resource.base64 === 'string' && resource.base64.length > MAX_BASE64_LENGTH && !issues.includes('INVALID_ENTRY_BYTES')) issues.push('INVALID_ENTRY_BYTES');
    }
  }
  if (totalBytes > MAX_TOTAL_BYTES) issues.push('TOTAL_BYTES_LIMIT_EXCEEDED');
  if (saveBodyIssue(resources)) issues.push('SAVE_BODY_BUDGET_EXCEEDED');
  return { issues, entries: resources.length, totalBytes };
}

export function activateAsyncLifecycle(mounted, operationSequence, inspectionSequence) {
  mounted.current = true;
  return () => {
    mounted.current = false;
    operationSequence.current += 1;
    inspectionSequence.current += 1;
  };
}

export function asyncTarget(assetId, revision, identity, sequence) {
  return `${assetId}\n${revision}\n${identity}\n${sequence}`;
}

export function acceptsAsyncTarget(expected, current) {
  return expected === current;
}
