export const MAX_TEXT_DOWNLOAD_BYTES = 1024 * 1024;

const MEDIA_EXTENSIONS = new Map([
  ['text/markdown; charset=utf-8', '.md'],
  ['text/plain; charset=utf-8', '.txt'],
]);

export function validateTextDownload({ filename, mediaType, content }) {
  if (typeof filename !== 'string' || filename.length < 1 || filename.length > 128 ||
      filename === '.' || filename === '..' || /[\\/]/u.test(filename) ||
      Array.from(filename).some(character => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) {
    return '下载文件名无效';
  }
  const extension = MEDIA_EXTENSIONS.get(mediaType);
  if (!extension || !filename.toLowerCase().endsWith(extension)) return '下载格式无效';
  if (typeof content !== 'string' || content.length === 0) return '没有可下载的文本';
  if (new TextEncoder().encode(content).byteLength > MAX_TEXT_DOWNLOAD_BYTES) return '下载文本过大';
  return '';
}

export function textDownloadError(payload, isValid, validationErrors = []) {
  if (typeof payload.content === 'string' && payload.content.length === 0) {
    return '尚未生成下载内容';
  }
  if (isValid === false) return validationErrors[0] || '请先保存当前修改';
  return validateTextDownload(payload);
}

export function downloadText(payload, platform = globalThis) {
  const error = validateTextDownload(payload);
  if (error) throw new Error(error);
  const blob = new platform.Blob([payload.content], { type: payload.mediaType });
  const url = platform.URL.createObjectURL(blob);
  const anchor = platform.document.createElement('a');
  anchor.href = url;
  anchor.download = payload.filename;
  anchor.rel = 'noopener';
  anchor.hidden = true;
  platform.document.body.append(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    platform.setTimeout(() => platform.URL.revokeObjectURL(url), 0);
  }
}
