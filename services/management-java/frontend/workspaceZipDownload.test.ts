import { strict as assert } from 'assert';
import { decodeWorkspaceZipBase64, resolveWorkspaceZipFileName } from './workspaceZipDownload';

const run = () => {
  assert.equal(
    resolveWorkspaceZipFileName('store-diagnostic', 'store-diagnostic.zip'),
    'store-diagnostic.zip',
  );
  assert.throws(
    () => resolveWorkspaceZipFileName('store-diagnostic', 'other-skill.zip'),
    /下载文件名与 Skill code 不一致/,
  );
  assert.deepEqual(Array.from(decodeWorkspaceZipBase64('AAECf/8=')), [0, 1, 2, 127, 255]);
  assert.throws(() => decodeWorkspaceZipBase64(''), /ZIP 下载内容为空/);
  assert.throws(() => decodeWorkspaceZipBase64('not-base64'), /ZIP 下载内容不是合法 Base64/);
  console.log('PASS workspace ZIP download response validation');
};

run();
