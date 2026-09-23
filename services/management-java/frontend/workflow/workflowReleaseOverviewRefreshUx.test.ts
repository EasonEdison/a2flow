import { strict as assert } from 'assert';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const pageSource = readFileSync(
  resolve(process.cwd(), 'workflow/WorkflowOrchestrationPage.tsx'),
  'utf8',
);
const releaseTabStart = pageSource.indexOf('<Tabs.TabPane tab="发布"');
const releaseTabSource = pageSource.slice(releaseTabStart);

assert.notEqual(releaseTabStart, -1, 'Workflow detail renders the release tab');
assert.equal(
  releaseTabSource.includes("activeSection === 'publication'"),
  true,
  'release overview mounts only when entering publication so it always reads the latest digest',
);

console.log('workflowReleaseOverviewRefreshUx.test.ts PASS');
