import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

function tests(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .filter((entry) => !['node_modules', 'dist'].includes(entry.name))
    .flatMap((entry) => entry.isDirectory()
      ? tests(join(directory, entry.name))
      : entry.name.endsWith('.test.ts') ? [join(directory, entry.name)] : []);
}
const result = spawnSync(process.execPath, ['--import', 'tsx', '--test', ...tests(process.cwd())], { stdio: 'inherit' });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
