// @ts-check
import { ManagementClient, runPrtAuthoring } from './authoring-core.mjs';

const form = /** @type {HTMLFormElement} */ (document.querySelector('#authoring-form'));
const descriptorTextInput = /** @type {HTMLTextAreaElement} */ (document.querySelector('#descriptor-text'));
const fileInput = /** @type {HTMLInputElement} */ (document.querySelector('#descriptor-file'));
const targetInput = /** @type {HTMLInputElement} */ (document.querySelector('#target-key'));
const specialistInput = /** @type {HTMLInputElement} */ (document.querySelector('#specialist-ids'));
const includeWorkflow = /** @type {HTMLInputElement} */ (document.querySelector('#include-workflow'));
const specialistCode = /** @type {HTMLInputElement} */ (document.querySelector('#specialist-code'));
const workflowCode = /** @type {HTMLInputElement} */ (document.querySelector('#workflow-code'));
const runButton = /** @type {HTMLButtonElement} */ (document.querySelector('#run'));
const progress = /** @type {HTMLProgressElement} */ (document.querySelector('#progress'));
const log = /** @type {HTMLElement} */ (document.querySelector('#log'));
const error = /** @type {HTMLElement} */ (document.querySelector('#error'));
const resultSection = /** @type {HTMLElement} */ (document.querySelector('#result'));
const assets = /** @type {HTMLElement} */ (document.querySelector('#assets'));
const download = /** @type {HTMLButtonElement} */ (document.querySelector('#download-manifest'));
let manifest = null;
let completed = 0;
const checkpointKey = 'a2flow.readingContent.prtCheckpoint.v1';
const manifestKey = 'a2flow.readingContent.prtManifest.v1';

includeWorkflow.addEventListener('change', () => {
  specialistCode.disabled = !includeWorkflow.checked;
  workflowCode.disabled = !includeWorkflow.checked;
  specialistCode.required = includeWorkflow.checked;
});

try {
  const previous = JSON.parse(localStorage.getItem(manifestKey) || 'null');
  if (previous?.workflow?.workflowCode) workflowCode.value = previous.workflow.workflowCode;
} catch { /* Corrupt local convenience state is ignored; server identities remain authoritative. */ }

function append(message) {
  completed += 1;
  progress.value = Math.min(95, completed);
  log.textContent += `\n${message}`;
  log.scrollTop = log.scrollHeight;
}

function addAsset(type, key) {
  const row = document.createElement('tr');
  const kind = document.createElement('td'); kind.textContent = type;
  const identity = document.createElement('td'); const code = document.createElement('code'); code.textContent = key; identity.append(code);
  const target = document.createElement('td'); const link = document.createElement('a'); link.href = new URL('/', location.origin).href; link.target = '_blank'; link.rel = 'noopener'; link.textContent = '打开管理台'; target.append(link);
  row.append(kind, identity, target); assets.append(row);
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (runButton.disabled || !form.reportValidity()) return;
  const descriptorText = descriptorTextInput.value.trim();
  const descriptorFile = fileInput.files?.[0];
  if (!descriptorText && !descriptorFile) {
    error.textContent = '请粘贴 base64 descriptor，或选择对应的文本文件。';
    descriptorTextInput.focus();
    return;
  }
  runButton.disabled = true; error.textContent = ''; resultSection.hidden = true; assets.replaceChildren();
  log.textContent = '开始：只执行用户点击触发的 PRT authoring。'; progress.value = 1; completed = 1;
  try {
    const descriptorSetBase64 = descriptorText || (descriptorFile ? (await descriptorFile.text()).trim() : '');
    const client = new ManagementClient({ origin: location.origin, signal: AbortSignal.timeout(30 * 60_000), onProgress: append });
    let resumeCheckpoint = null;
    try { resumeCheckpoint = JSON.parse(localStorage.getItem(checkpointKey) || 'null'); } catch { localStorage.removeItem(checkpointKey); }
    manifest = await runPrtAuthoring(client, {
      descriptorSetBase64, targetKey: targetInput.value, specialistIds: specialistInput.value,
      includeWorkflow: includeWorkflow.checked, specialistCode: specialistCode.value, workflowCode: workflowCode.value.trim() || undefined,
      resumeCheckpoint,
      onCheckpoint: checkpoint => localStorage.setItem(checkpointKey, JSON.stringify(checkpoint)),
    });
    for (const item of manifest.capabilities) addAsset('能力', `${item.actionCode} / ${item.draftId}`);
    for (const item of manifest.applications) addAsset('Application', item.appCode);
    for (const item of manifest.skills) addAsset('Skill', item.skillCode);
    if (manifest.workflow) addAsset('Workflow', manifest.workflow.workflowCode);
    addAsset('Catalog', manifest.catalog.catalogId);
    append('完成：所有返回资产均已核对真实 PRT sourceId。'); progress.value = 100;
    localStorage.removeItem(checkpointKey); localStorage.setItem(manifestKey, JSON.stringify(manifest));
    resultSection.hidden = false;
  } catch (reason) {
    error.textContent = reason instanceof Error ? reason.message : '未知错误';
    append('停止：没有自动重试失败的发布操作。修正问题后可再次点击；脚本会按稳定 Key 复用已有资产。');
  } finally {
    runButton.disabled = false;
  }
});

download.addEventListener('click', () => {
  if (!manifest) return;
  const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
  anchor.href = url; anchor.download = 'reading-content-prt-manifest.json'; anchor.click(); URL.revokeObjectURL(url);
});
