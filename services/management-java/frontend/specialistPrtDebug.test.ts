import { strict as assert } from 'assert';
import {
  buildSpecialistDebugOptions,
  buildSpecialistPrtBindingRequest,
  buildSpecialistManagementUrl,
  resolveSpecialistDebugSelection,
  resolveSpecialistPrtAction,
  SKILL_FACTORY_TAB_ITEMS,
} from './specialistPrtDebug';

assert.deepEqual(
  SKILL_FACTORY_TAB_ITEMS.map((item) => [item.key, item.label]),
  [
    ['overview', '基础信息'],
    ['capabilities', '业务能力'],
    ['components', '渲染组件'],
    ['files', '文件处理'],
    ['release', '打包发布'],
    ['binding', '调试页面'],
  ],
);

assert.deepEqual(resolveSpecialistPrtAction({ versionAction: 'REUSE' }), {
  action: 'REUSE',
  label: '绑定到当前 PRT 变更并发布',
});
assert.deepEqual(resolveSpecialistPrtAction({ versionAction: 'CREATE' }), {
  action: 'CREATE',
  label: '新建 PRT 变更并绑定发布',
});
assert.equal(resolveSpecialistPrtAction({ versionAction: 'REUSE', prtEffective: true }), undefined);
assert.equal(resolveSpecialistPrtAction({ versionAction: 'BLOCKED' }), undefined);
assert.equal(buildSpecialistManagementUrl('12'), '/employee/12');
assert.deepEqual(buildSpecialistPrtBindingRequest('QUERY', '12', 'skill-a', 'tester'), {
  path: '/api/management/v2/handler',
  body: {
    userName: 'tester',
    method: 'QUERY_EMPLOYEE_PRT_SKILL_BINDING',
    params: {
      employeeId: '12',
      skillCode: 'skill-a',
    },
  },
});
assert.deepEqual(buildSpecialistPrtBindingRequest('PUBLISH', '12', 'skill-a', 'tester'), {
  path: '/api/management/v2/handler',
  body: {
    userName: 'tester',
    method: 'BIND_AND_PUBLISH_EMPLOYEE_PRT_SKILL',
    params: {
      employeeId: '12',
      skillCode: 'skill-a',
    },
  },
});

const specialistOptions = buildSpecialistDebugOptions([
  {
    employeeId: '2',
    employeeCode: 'customer-service',
    content: { name: '客服专员' },
  },
  {
    employeeId: 1,
    employeeCode: 'manager',
    content: { name: '店长' },
  },
  {
    employeeId: '2',
    employeeCode: 'customer-service-copy',
    content: { name: '重复客服专员' },
  },
]);
assert.deepEqual(specialistOptions, [
  { value: '2', label: '客服专员（employeeId=2）', employeeName: '客服专员' },
  { value: '1', label: '店长（employeeId=1）', employeeName: '店长' },
]);
assert.equal(resolveSpecialistDebugSelection('', ['1'], specialistOptions), '1');
assert.equal(resolveSpecialistDebugSelection('2', ['1'], specialistOptions), '2');
assert.equal(resolveSpecialistDebugSelection('3', ['1'], specialistOptions), '1');
assert.equal(resolveSpecialistDebugSelection('', ['3'], specialistOptions), '');

console.log('PASS specialist PRT debug contract');
