---
name: activity-confirm-schedule
description: 基于已选活动方案提出可执行安排选项，并通过专用确认卡取得明确确认。
---

# 确认执行安排

你根据调用方提供的已选方案和事实约束，整理二到八个可执行安排选项。
若没有明确的已选方案，应说明缺口，不替用户选择，也不把猜测当作确认。

每个安排应清楚表达日期或阶段、地点或线上形式、参与方式、负责人边界和
仍待补充的信息。不要虚构报价、库存、场地可用性、报名链接或外部执行结果。

必须先通过当前上下文中的 use_skill 取得本文，再使用已授权的
render_application。Application 标识只能是
activity-package.confirm-schedule；data 只能包含 prompt 和 options。
options 为二到八个对象，每项只能包含非空 label 和稳定的非空 value。

确认只能来自卡片 confirm_schedule Action 的已保存成功结果，Action 输入
必须包含所选 optionId 和 confirmed=true。普通聊天、模型判断或卡片展示
成功均不构成确认。不要自动重试、替用户确认或调用下游节点。

收到有效确认后，输出一份执行安排简报，明确所选安排、采用的上游方案、
已确认事实和待补齐事项。该结果供调用方使用。

本 Skill 可以独立使用：只要调用方提供一个明确方案，它即可完成安排确认；
它不依赖固定 Workflow，不包含业务图路由，也不直接访问数据库或外部系统。
