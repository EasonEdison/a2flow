import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import { spawn } from 'node:child_process';

const playwrightPath = process.env.PLAYWRIGHT_PATH;
if (!playwrightPath) throw new Error('PLAYWRIGHT_PATH 必须指向已安装的 playwright 模块目录');
const require = createRequire(import.meta.url);
const { chromium } = require(playwrightPath);

const root = new URL('..', import.meta.url).pathname;
const output = `${root}qa-output`;
await mkdir(output, { recursive: true });
const server = spawn('npm', ['run', 'dev', '--', '--port', '4173'], { cwd: root, stdio: 'pipe' });
await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('Vite 启动超时')), 15000);
  server.stdout.on('data', (data) => {
    if (String(data).includes('4173')) {
      clearTimeout(timer);
      resolve();
    }
  });
  server.on('exit', (code) => reject(new Error(`Vite 提前退出 ${code}`)));
});

const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const browser = await chromium.launch({ executablePath: chrome, headless: true });
const errors = [];
let session = null;
let runState = 'WAITING';
let schedules = [];
let notifications = [
  { id: 'n1', type: 'WAITING', title: '活动方案等待确认', relatedType: 'run', relatedId: 'run-1', read: false, createdAt: '2026-09-19T09:00:00Z' },
  { id: 'n2', type: 'COMPLETED', title: '周报生成已完成', relatedType: 'run', relatedId: 'run-2', read: false, createdAt: '2026-09-18T09:00:00Z' },
];
const workflows = [
  { key: 'activity', name: '活动策划助手', description: '生成活动方案并等待确认', inputHint: '描述人数、预算与偏好' },
  { key: 'weekly', name: '经营周报助手', description: '汇总经营数据并生成周报', inputHint: '输入统计周期' },
];
const runs = [
  { id: 'run-1', workflowKey: 'activity', title: '周末活动策划', status: 'WAITING', input: '为 12 位同事策划周末活动', createdAt: '2026-09-19T08:00:00Z' },
  { id: 'run-2', workflowKey: 'weekly', title: '经营周报', status: 'SUCCEEDED', input: '本周经营情况', createdAt: '2026-09-18T08:00:00Z' },
];
const messages = [
  { id: 'm1', role: 'assistant', text: '你好，我可以帮你运行企业工作流。', createdAt: '2026-09-19T08:00:00Z' },
];
const conversations = [{ id: 'c1', title: '活动策划', updatedAt: '2026-09-19T08:00:00Z' }];

function runView(id = 'run-1') {
  return {
    id,
    title: '周末活动策划',
    lifecycle: runState,
    requirement: '为 12 位同事策划周末活动',
    nodes: [
      {
        id: 'choose_plan', title: '活动方案选择', status: runState, summary: runState === 'WAITING' ? '请选择活动方案' : '方案已确认', records: [],
        card: runState === 'WAITING' ? { kind: 'INTERACTIVE', id: 'card-1', prompt: '请选择活动方案', choices: [{ value: 'indoor', label: '室内工作坊' }, { value: 'outdoor', label: '户外交流' }], operable: true, actionName: 'select_activity_plan', interactionId: 'interaction-1', buttonLabel: '确认方案', confirmed: false } : undefined,
        output: runState === 'SUCCEEDED' ? '已选择室内工作坊，活动方案生成完成。' : undefined,
      },
      { id: 'package', title: '生成活动包', status: runState === 'SUCCEEDED' ? 'SUCCEEDED' : 'PENDING', summary: '生成最终结果', records: [] },
    ],
  };
}

async function installFixtures(page) {
  await page.route('**://*/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const body = request.postDataJSON?.() ?? {};
    const json = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (path === '/api/auth/session') return session ? json(session) : json({ error: { code: 'UNAUTHENTICATED' } }, 401);
    if (path === '/api/auth/register' || path === '/api/auth/login') { session = { userId: 'u1', username: body.username, role: '管理员' }; return json(session); }
    if (path === '/api/auth/logout') { session = null; return json({ ok: true }); }
    if (path === '/api/conversations' && method === 'GET') return json({ items: conversations });
    if (path === '/api/conversations' && method === 'POST') return json(conversations[0]);
    if (path.endsWith('/messages') && method === 'GET') return json({ items: messages });
    if (path.endsWith('/messages') && method === 'POST') {
      messages.push({ id: `m${messages.length + 1}`, role: 'user', text: body.text, createdAt: new Date().toISOString() });
      messages.push({ id: `m${messages.length + 1}`, role: 'assistant', text: '我找到了合适的工作流，请确认后运行。', createdAt: new Date().toISOString(), event: { type: 'workflow_confirm', workflowKey: 'activity', title: '活动策划助手' } });
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'data: {"type":"text","text":"我找到了合适的工作流，请确认后运行。"}\n\ndata: {"type":"workflow_confirm","workflowKey":"activity","title":"活动策划助手"}\n\ndata: {"type":"done"}\n\n' });
    }
    if (path === '/api/workflows') return json({ items: workflows });
    if (path === '/api/runs' && method === 'GET') return json({ items: runs });
    if (path === '/api/runs' && method === 'POST') return json({ runId: 'run-1' });
    if (path === '/api/runs/run-1' && method === 'GET') return json(runView());
    if (path === '/api/runs/run-1/actions') { runState = 'SUCCEEDED'; runs[0].status = 'SUCCEEDED'; return json({ ok: true }); }
    if (path === '/api/runs/run-1/stop') { runState = 'STOPPED'; runs[0].status = 'STOPPED'; return json({ ok: true }); }
    if (path === '/api/schedules' && method === 'GET') return json({ items: schedules });
    if (path === '/api/schedules' && method === 'POST') { const item = { id: 's1', workflowKey: body.workflowKey, workflowName: '活动策划助手', input: body.input, cadence: body.cadence, enabled: true, nextRunAt: '2026-09-20T09:00:00Z' }; schedules.push(item); return json(item); }
    if (path === '/api/schedules/s1' && method === 'PATCH') { schedules = schedules.map((item) => ({ ...item, enabled: body.enabled })); return json(schedules[0]); }
    if (path === '/api/schedules/s1' && method === 'DELETE') { schedules = []; return json({ ok: true }); }
    if (path === '/api/notifications') return json({ items: notifications });
    if (path === '/api/notifications/n1/read') { notifications = notifications.map((item) => item.id === 'n1' ? { ...item, read: true } : item); return json({ ok: true }); }
    return json({ error: { code: `UNHANDLED_${method}_${path}` } }, 500);
  });
}

try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().includes('status of 401')) errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  await installFixtures(page);
  await page.goto('http://127.0.0.1:4173');
  await page.getByRole('button', { name: '注册账号' }).click();
  await page.getByLabel('用户名').fill('demo-admin');
  await page.getByLabel('密码').fill('password123');
  await page.getByRole('button', { name: '注册并登录' }).click();
  await page.getByPlaceholder('输入消息，描述你想完成的工作').fill('帮我策划周末活动');
  await page.getByRole('button', { name: '发送' }).click();
  await page.getByRole('button', { name: '运行工作流' }).click();
  await page.getByLabel('请选择活动方案').getByText('室内工作坊').click();
  await page.getByRole('button', { name: '确认方案' }).click();
  await assert.doesNotReject(() => page.getByText('活动方案生成完成').waitFor());
  await page.getByRole('button', { name: '工作流中心' }).click();
  await page.locator('.workflow-catalog-card').first().waitFor();
  assert.equal(await page.locator('.workflow-catalog-card').count(), 2);
  await page.getByRole('tab', { name: '我的运行' }).click();
  await page.getByText('周末活动策划').first().click();
  await page.getByRole('button', { name: '定时管理' }).click();
  await page.getByLabel('执行输入').fill('每周活动计划');
  await page.getByRole('button', { name: '创建定时任务' }).click();
  await page.getByRole('switch').click();
  await page.getByRole('button', { name: '删除' }).click();
  await page.getByRole('button', { name: /通知中心/ }).last().click();
  assert.equal(await page.locator('.notification-item').count(), 2);
  await page.getByRole('button', { name: '标记已读' }).first().click();
  await page.screenshot({ path: `${output}/desktop.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '打开导航' }).click();
  await page.screenshot({ path: `${output}/narrow.png`, fullPage: true });
  await page.getByRole('button', { name: '退出登录' }).click();
  await page.getByText('登录 A2Flow').waitFor();
  await page.getByLabel('用户名').fill('demo-admin');
  await page.getByLabel('密码').fill('password123');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.waitForTimeout(500);
  if (!(await page.getByText('数字员工对话').count())) {
    throw new Error(`重新登录后页面异常：${(await page.locator('body').innerText()).slice(0, 500)}`);
  }
  await page.getByText('数字员工对话').waitFor();
  assert.deepEqual(errors, []);
  await context.close();

  const preview = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await preview.goto('http://127.0.0.1:4173/?preview=fixture');
  await preview.getByText('开发示例 · Fixture').waitFor();
  await preview.close();
} finally {
  await browser.close();
  server.kill('SIGTERM');
}
