import type { NodeStatus, RunView } from '../presentation';

export type FixtureState = 'RUNNING' | 'WAITING' | 'SUCCEEDED' | 'UNCONFIRMED' | 'STOPPED';

export function fixture(
  state: FixtureState,
  requirement = '为 12 位同事策划一场周末活动，预算 2,400 元。',
): RunView {
  const ended = state === 'SUCCEEDED';
  const status: NodeStatus = state === 'UNCONFIRMED' ? 'UNKNOWN' : state;
  const activePlan = state === 'RUNNING' || state === 'UNCONFIRMED' ? undefined : {
    kind: 'INTERACTIVE' as const,
    id: 'fixture-plan-card',
    prompt: '请从以下活动方案中选择一个。',
    choices: [
      { value: 'indoor', label: '方案 A · 室内工作坊' },
      { value: 'outdoor', label: '方案 B · 户外交流' },
    ],
    operable: state === 'WAITING',
    actionName: 'select_activity_plan',
    interactionId: 'fixture-plan-interaction',
    buttonLabel: '选择这个方案',
    confirmed: false,
  };

  return {
    id: 'fixture-run',
    title: '周末活动策划',
    lifecycle: status,
    requirement,
    nodes: [
      {
        id: 'choose_plan',
        title: '活动方案选择',
        status: ended ? 'SUCCEEDED' : status,
        summary: ended
          ? '活动方案已确认'
          : state === 'WAITING'
            ? '方案已生成，请选择你喜欢的安排'
            : state === 'UNCONFIRMED'
              ? '执行结果未确认，请查看运行记录'
              : '结合活动需求，准备适合大家的方案',
        records: [
          { id: 'r1', kind: 'reasoning', text: '这是一条开发示例：结合人数与预算，比较室内工作坊和户外交流两种安排。' },
          { id: 'r2', kind: 'operation', text: '示例执行记录：读取活动需求。' },
        ],
        card: activePlan,
        output: ended ? '已选择室内工作坊。主题分享、分组交流与轻松互动。' : undefined,
      },
      {
        id: 'confirm_schedule',
        title: '执行安排确认',
        status: ended ? 'SUCCEEDED' : 'PENDING',
        summary: ended ? '执行安排已确认' : '根据选中的活动方案确认执行安排',
        records: ended ? [{ id: 's1', kind: 'text', text: '开发示例：场地与时段已确认。' }] : [],
        output: ended ? '周六 14:00–17:00，创意空间 A。' : undefined,
      },
      {
        id: 'show_activity_package',
        title: '最终活动包',
        status: ended ? 'SUCCEEDED' : 'PENDING',
        summary: ended ? '最终活动包已生成' : '等待活动方案与执行安排确认',
        records: [],
        card: ended ? {
          kind: 'DISPLAY_ONLY' as const,
          id: 'fixture-package-card',
          title: '最终活动包',
          fields: [
            { label: '已选方案', markdown: '室内工作坊' },
            { label: '确认安排', markdown: '周六 14:00–17:00，创意空间 A' },
            { label: '活动包摘要', markdown: '主题分享、分组交流与轻松互动。' },
          ],
        } : undefined,
      },
    ],
  };
}
