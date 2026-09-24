import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { Catalog } from '@a2ui/web_core/v0_9';
import { EqualsImplementation } from '@a2ui/web_core/v0_9/basic_catalog';
import { basicCatalog } from '@a2ui/react/v0_9';
import {
  contractFunctionCodes,
  officialFunctionCodes,
  selectFunctionImplementations,
} from '../src/catalogFunctions.mjs';
import { textDownloadError } from '../src/textDownload.mjs';

const contract = JSON.parse(await readFile(
  new URL('../src/catalogs/digital-employee-functions.json', import.meta.url),
  'utf8',
));
const expectedOfficialCodes = [
  'required',
  'regex',
  'length',
  'numeric',
  'email',
  'formatString',
  'formatNumber',
  'formatCurrency',
  'formatDate',
  'pluralize',
  'openUrl',
  'and',
  'or',
  'not',
];

function createFunctionCatalog(id, codes, extensions = {}) {
  return new Catalog(id, [], selectFunctionImplementations(
    codes,
    basicCatalog.functions,
    extensions,
  ));
}

test('function contract is exactly official Basic 14 plus SDK equals', () => {
  assert.deepEqual(officialFunctionCodes(contract), expectedOfficialCodes);
  assert.deepEqual(contractFunctionCodes(contract), [...expectedOfficialCodes, 'equals']);
  assert.equal(officialFunctionCodes(contract).length, 14);
  assert.equal(contractFunctionCodes(contract).length, 15);
  assert.deepEqual(contract.sdkExtensions.equals, {
    package: '@a2ui/web_core',
    version: '0.11.0',
    export: 'EqualsImplementation',
    semantics: 'strict equality',
  });

  for (const code of expectedOfficialCodes) {
    assert.deepEqual(contract.functions[code], {
      $ref: `${contract.baseCatalog.catalogId}#/functions/${code}`,
    });
  }
});

test('renderer exposes no SDK functions outside the 14 plus equals allowlist', () => {
  const officialCatalog = createFunctionCatalog(
    contract.baseCatalog.catalogId,
    officialFunctionCodes(contract),
  );
  const projectCatalog = createFunctionCatalog(
    contract.catalogId,
    contractFunctionCodes(contract),
    { equals: EqualsImplementation },
  );

  assert.equal(officialCatalog.functions.size, 14);
  assert.equal(projectCatalog.functions.size, 15);
  assert.throws(
    () => officialCatalog.invoker('equals', { a: 'same', b: 'same' }, {}),
    /Function not found/u,
  );
  assert.equal(projectCatalog.invoker('equals', { a: 'same', b: 'same' }, {}), true);
  assert.equal(projectCatalog.invoker('equals', { a: 1, b: '1' }, {}), false);
  assert.throws(
    () => projectCatalog.invoker('add', { a: 1, b: 2 }, {}),
    /Function not found/u,
  );
});

test('equals and official and keep stale-export checks blocked', () => {
  const projectCatalog = createFunctionCatalog(
    contract.catalogId,
    contractFunctionCodes(contract),
    { equals: EqualsImplementation },
  );
  const titleMatches = projectCatalog.invoker(
    'equals',
    { a: '已保存标题', b: '已保存标题' },
    {},
  );
  const markdownMatches = projectCatalog.invoker(
    'equals',
    { a: '# 未保存修改', b: '# 已保存正文' },
    {},
  );
  const checksValid = projectCatalog.invoker(
    'and',
    { values: [titleMatches, markdownMatches] },
    {},
  );
  const exportPayload = {
    filename: 'manuscript.md',
    mediaType: 'text/markdown; charset=utf-8',
    content: '# 旧导出结果',
  };

  assert.equal(checksValid, false);
  assert.equal(
    textDownloadError(exportPayload, checksValid, ['请先保存当前修改']),
    '请先保存当前修改',
  );
});
