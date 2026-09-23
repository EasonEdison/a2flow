// 仅配合新建的 loopback management_host_test 库使用，绝不连接已有应用库。
// 登录上游是协议夹具；Java、Spring请求作用域、MyBatis和数据库会话读取使用真实实现。
import assert from 'node:assert/strict';
import { createHash, randomUUID } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { createServer } from 'node:http';

const origin = 'http://127.0.0.1:18790';
const token = 'a'.repeat(43);
const cookie = `a2flow_management_session=${token}`;
const hash = createHash('sha256').update(token).digest('hex');
const skillCode = `http-smoke-${randomUUID()}`;
const psql = process.env.PSQL;
assert.ok(psql, 'PSQL 必须指定本机测试客户端');
function sql(input) {
  return execFileSync(psql, ['-h', '127.0.0.1', '-p', '56478', '-d', 'management_host_test', '-v', 'ON_ERROR_STOP=1', '-At'],
    { input, encoding: 'utf8' }).trim();
}
sql(`CREATE TABLE users (user_id bigint PRIMARY KEY, role text NOT NULL);
CREATE TABLE sessions (token_sha256 text PRIMARY KEY, user_id bigint REFERENCES users(user_id), expires_at timestamptz NOT NULL);
INSERT INTO users VALUES (9223372036854775807, 'ADMIN');
INSERT INTO sessions VALUES ('${hash}', 9223372036854775807, CURRENT_TIMESTAMP + INTERVAL '1 hour');`);
let loginCalls = 0;
const account = createServer(async (req, res) => {
  loginCalls++;
  if (req.method === 'GET') return res.end('synthetic account login');
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  assert.equal(Buffer.concat(chunks).toString(), 'username=fixture&password=not-a-real-password');
  assert.equal(req.headers.origin, origin);
  res.writeHead(303, { Location: '/', 'Set-Cookie': `${cookie}; Path=/; HttpOnly; SameSite=Lax` });
  res.end();
});
await new Promise(resolve => account.listen(18791, '127.0.0.1', resolve));
async function post(body, extra = {}, path = '/api/management/v2/handler') {
  const headers = { 'Content-Type': 'application/json', Origin: origin, Cookie: cookie, ...extra };
  for (const key of Object.keys(headers)) if (headers[key] === undefined) delete headers[key];
  const response = await fetch(origin + path, { method: 'POST', headers, body: JSON.stringify(body), redirect: 'manual' });
  return { status: response.status, text: await response.text(), headers: response.headers };
}
function envelope(text) {
  if (!text.startsWith('data: ')) return JSON.parse(text);
  assert.ok(text.endsWith('data: [DONE]\n\n'));
  return JSON.parse(text.split('\n')[0].slice(6));
}
try {
  for (const page of ['/', '/management', '/management/components/a2ui-applications/edit?id=49']) {
    const response = await fetch(origin + page);
    assert.equal(response.status, 200, page);
    assert.match(await response.text(), /<div id="root">/);
  }
  assert.equal((await fetch(origin + '/assets/does-not-exist.js')).status, 404);
  const body = { method: 'SKILL_LIST', params: {} };
  assert.equal((await post(body, { Cookie: undefined })).status, 401);
  assert.equal((await post(body, { Origin: undefined })).status, 403);
  assert.equal((await post(body, { Origin: 'https://not-allowed.example' })).status, 403);
  assert.equal((await post(body, { 'X-User-Id': '1' })).status, 403);
  assert.equal((await post({ ...body, params: { userId: '1' } })).status, 403);
  assert.equal((await post(body, { Cookie: `${cookie}; ${cookie}` })).status, 401);
  for (const method of ['SKILL_LIST', 'COMPONENT_LIST', 'WORKFLOW_LIST', 'SKILL_FACTORY_CONFIG']) {
    const reply = await post({ method, params: {} });
    assert.equal(reply.status, 200, `${method}: ${reply.text}`);
    assert.equal(envelope(reply.text).result, 1, `${method}: ${reply.text}`);
  }
  const plain = await post(body, {}, '/api/management/v2/bizrender');
  assert.match(plain.headers.get('content-type'), /application\/json/);
  assert.equal(envelope(plain.text).result, 1);
  assert.equal((await post(body, {}, '/api/management/v2/chat')).status, 409);
  assert.equal(envelope((await post({ method: 'CODING_CHAT', params: {} })).text).result, 0);
  const created = envelope((await post({ method: 'WORKSPACE_CREATE', params: {
    skillCode, skillNameCn: 'HTTP创建检查', skillDescription: '隔离测试资产', specialistIds: '101'
  } })).text);
  assert.equal(created.result, 1, JSON.stringify(created));
  assert.equal(sql(`SELECT count(*) FROM skill_draft WHERE skill_code='${skillCode}'`), '1');
  const content = `---\nname: ${skillCode}\ndescription: 隔离测试资产\n---\n\n# 手填指令\n`;
  const saved = envelope((await post({ method: 'WORKSPACE_FILE_SAVE', params: {
    workspaceId: skillCode, skillCode, filePath: 'SKILL.md', content
  } })).text);
  assert.equal(saved.result, 1, JSON.stringify(saved));
  const tree = envelope((await post({ method: 'WORKSPACE_TREE', params: { workspaceId: skillCode } })).text);
  assert.equal(tree.result, 1, JSON.stringify(tree));
  assert.match(tree.data, /SKILL\.md/);
  const restored = envelope((await post({ method: 'WORKSPACE_FILE_CONTENT', params: {
    workspaceId: skillCode, filePath: 'SKILL.md'
  } })).text);
  assert.equal(restored.result, 1, JSON.stringify(restored));
  assert.equal(JSON.parse(restored.data).content, content);
  sql("UPDATE users SET role='USER';");
  const denied = envelope((await post({ method: 'WORKSPACE_CREATE', params: { skillCode: 'host-smoke', name: 'smoke', specialistIds: '101' } })).text);
  assert.equal(denied.result, 0, JSON.stringify(denied));
  assert.match(JSON.stringify(denied), /PERMISSION_DENIED|ADMIN_REQUIRED/);
  assert.equal(envelope((await post(body)).text).result, 1);
  sql("UPDATE sessions SET expires_at=CURRENT_TIMESTAMP - INTERVAL '1 second';");
  assert.equal((await post(body)).status, 401);
  assert.equal((await fetch(origin + '/login')).status, 200);
  const login = await fetch(origin + '/login', { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'username=fixture&password=not-a-real-password', redirect: 'manual' });
  assert.equal(login.status, 303);
  assert.equal(login.headers.get('location'), '/');
  assert.match(login.headers.get('set-cookie'), /HttpOnly/);
  const calls = loginCalls;
  assert.equal((await fetch(origin + '/login', { method: 'POST', body: 'blocked' })).status, 403);
  assert.equal(loginCalls, calls, '无Origin请求不得触达登录上游');
  console.log('PASS: 真实Java HTTP / Spring作用域 / PG会话权限 / SSE / 页面刷新 / 登录代理协议');
  console.log('边界: 登录上游为夹具；不代表真实账号服务、公网部署或发布链路验收。');
} finally {
  account.closeAllConnections();
  await new Promise(resolve => account.close(resolve));
}
