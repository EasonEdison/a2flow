import { strict as assert } from 'node:assert';
import { normalizeUserIdWhitelist } from './userIdWhitelist';

assert.equal(normalizeUserIdWhitelist('9223372036854775807,0,-9223372036854775808,-1,0'), '-9223372036854775808,-1,0,9223372036854775807');
for (const value of ['9223372036854775808', '-9223372036854775809', '-0', '00', '01', '+1', '1.1', '1e3', '1,']) assert.equal(normalizeUserIdWhitelist(value), undefined);
assert.equal(normalizeUserIdWhitelist(''), '');
console.log('PASS signed64 userId boundaries and canonical decimal wire representation');
