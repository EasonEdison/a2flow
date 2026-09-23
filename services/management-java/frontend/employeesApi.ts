import type { SpecialistDebugEmployeeSource } from './specialistPrtDebug';

export async function listDigitalEmployeeDefinitions(query: { pageNo: number; pageSize: number }): Promise<{ list: SpecialistDebugEmployeeSource[]; total: number }> {
  const response = await fetch(`/api/management/employees?${new URLSearchParams({ pageNo: String(query.pageNo), pageSize: String(query.pageSize) })}`, { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`员工目录接口尚不可用（HTTP ${response.status}），无法加载调试专员`);
  const result: unknown = await response.json();
  if (!result || typeof result !== 'object' || !('list' in result) || !Array.isArray(result.list) || !('total' in result) || typeof result.total !== 'number') {
    throw new Error('员工目录接口返回格式无效，要求 {list, total}');
  }
  const list = result.list.map((item: unknown) => {
    if (!item || typeof item !== 'object' || !('employeeId' in item) || !['string', 'number'].includes(typeof item.employeeId)) throw new Error('员工目录缺少有效 employeeId');
    return item as SpecialistDebugEmployeeSource;
  });
  return { list, total: result.total };
}
