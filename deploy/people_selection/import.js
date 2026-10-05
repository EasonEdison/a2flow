// @ts-check
import { ManagementClient, runPrtAuthoring } from './authoring-core.mjs';

const form = /** @type {HTMLFormElement} */ (document.querySelector('#authoring-form'));
const loadDescriptor = /** @type {HTMLButtonElement} */ (document.querySelector('#load-project-descriptor'));
const descriptorStatus = /** @type {HTMLElement} */ (document.querySelector('#descriptor-status'));
const descriptorText = /** @type {HTMLTextAreaElement} */ (document.querySelector('#descriptor-text'));
const descriptorFile = /** @type {HTMLInputElement} */ (document.querySelector('#descriptor-file'));
const targetKey = /** @type {HTMLInputElement} */ (document.querySelector('#target-key'));
const specialistIds = /** @type {HTMLInputElement} */ (document.querySelector('#specialist-ids'));
const run = /** @type {HTMLButtonElement} */ (document.querySelector('#run'));
const progress = /** @type {HTMLProgressElement} */ (document.querySelector('#progress'));
const log = /** @type {HTMLElement} */ (document.querySelector('#log'));
const error = /** @type {HTMLElement} */ (document.querySelector('#error'));
const result = /** @type {HTMLElement} */ (document.querySelector('#result'));
const manifestView = /** @type {HTMLElement} */ (document.querySelector('#manifest'));
const download = /** @type {HTMLButtonElement} */ (document.querySelector('#download-manifest'));
let manifest = null;
let completed = 0;

function validateDescriptorBase64(value) {
  const descriptor = value.trim();
  if (!descriptor || descriptor.length % 4 !== 0 || !/^[A-Za-z0-9+/]+={0,2}$/.test(descriptor)) {
    throw new Error('Content RPC descriptor 不是合法的 base64 文本。');
  }
  let decoded;
  try { decoded = atob(descriptor); } catch { throw new Error('Content RPC descriptor 无法解码。'); }
  if (!decoded.length) throw new Error('Content RPC descriptor 解码结果为空。');
  return descriptor;
}

function append(message) {
  completed += 1; progress.value = Math.min(95, completed * 5);
  log.textContent += `\n${message}`; log.scrollTop = log.scrollHeight;
}

loadDescriptor.addEventListener('click', async () => {
  loadDescriptor.disabled = true; error.textContent = ''; descriptorStatus.textContent = '正在加载…';
  try {
    const response = await fetch(new URL('./content-descriptor.txt', import.meta.url), { cache: 'no-store' });
    if (!response.ok) throw new Error(`加载契约失败（HTTP ${response.status}）`);
    descriptorText.value = validateDescriptorBase64(await response.text());
    descriptorStatus.textContent = '已加载并校验，请继续审阅。';
  } catch (reason) {
    descriptorStatus.textContent = '';
    error.textContent = reason instanceof Error ? reason.message : '加载契约失败。';
  } finally { loadDescriptor.disabled = false; }
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (run.disabled || !form.reportValidity()) return;
  const pasted = descriptorText.value.trim();
  const file = descriptorFile.files?.[0];
  if (!pasted && !file) { error.textContent = '请加载、粘贴或上传 descriptor。'; return; }
  run.disabled = true; error.textContent = ''; result.hidden = true;
  log.textContent = '开始：只执行本次用户点击触发的 PRT authoring。'; progress.value = 1; completed = 1;
  try {
    const descriptorSetBase64 = validateDescriptorBase64(pasted || (file ? await file.text() : ''));
    const client = new ManagementClient({ origin: location.origin, signal: AbortSignal.timeout(30 * 60_000), onProgress: append });
    manifest = await runPrtAuthoring(client, {
      descriptorSetBase64, targetKey: targetKey.value, specialistIds: specialistIds.value,
    });
    manifestView.textContent = JSON.stringify(manifest, null, 2);
    result.hidden = false; progress.value = 100;
    append('完成：资产已发布到 PRT；未执行 ONLINE。');
  } catch (reason) {
    error.textContent = reason instanceof Error ? reason.message : '未知错误';
    append('停止：失败操作不会自动重试。');
  } finally { run.disabled = false; }
});

download.addEventListener('click', () => {
  if (!manifest) return;
  const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
  anchor.href = url; anchor.download = 'people-selection-prt-manifest.json'; anchor.click(); URL.revokeObjectURL(url);
});
