export function resolveWorkspaceZipFileName(skillCode: string, responseFileName: string): string {
  const expectedFileName = `${String(skillCode || '').trim()}.zip`;
  if (expectedFileName === '.zip' || responseFileName !== expectedFileName) {
    throw new Error('ZIP 下载文件名与 Skill code 不一致');
  }
  return expectedFileName;
}

export function decodeWorkspaceZipBase64(zipBase64: string): Uint8Array {
  const normalized = String(zipBase64 || '').trim();
  if (!normalized) {
    throw new Error('ZIP 下载内容为空');
  }
  let binary = '';
  try {
    binary = atob(normalized);
  } catch {
    throw new Error('ZIP 下载内容不是合法 Base64');
  }
  if (!binary.length) {
    throw new Error('ZIP 下载内容为空');
  }
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

export function triggerWorkspaceZipDownload(fileName: string, bytes: Uint8Array): void {
  const downloadBytes = new Uint8Array(bytes.length);
  downloadBytes.set(bytes);
  const url = URL.createObjectURL(new Blob([downloadBytes.buffer], { type: 'application/zip' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.style.display = 'none';
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    URL.revokeObjectURL(url);
  }
}
