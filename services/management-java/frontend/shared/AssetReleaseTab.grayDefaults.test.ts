import { readFileSync } from 'fs';
import { resolve } from 'path';

type GrayEnvironment = 'PRT' | 'ONLINE';

const source = readFileSync(
  resolve(process.cwd(), 'shared/AssetReleaseTab.tsx'),
  'utf8',
);

const grayPercentageOf = (environment: GrayEnvironment): string => {
  const match = source.match(new RegExp(`${environment}:\\s*\\{\\s*percentage:\\s*'([^']+)'`));
  if (!match) {
    throw new Error(`missing ${environment} gray percentage default`);
  }
  return match?.[1];
};

const assertEqual = (actual: string, expected: string, description: string) => {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${expected}, received ${actual}`);
  }
};

assertEqual(grayPercentageOf('PRT'), '100', 'PRT gray percentage default');
assertEqual(grayPercentageOf('ONLINE'), '10', 'ONLINE gray percentage default');

console.log('PASS PRT defaults to 100 while ONLINE remains 10');
