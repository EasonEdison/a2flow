---
name: activity-show-package
description: 汇总已选方案和已确认安排，展示可刷新读取的最终活动包，不发起交互等待。
---

# 展示最终活动包

你根据调用方提供的已选方案、已确认执行安排和原始活动要求，整理最终活动
包。若关键事实未确认，应在摘要中明确标注，不得自行补全或声称已经执行。

必须先通过当前上下文中的 use_skill 取得本文，再调用一次已授权的
render_application。Application 标识只能是 activity-package.display；
data 必须且只能包含四个非空字符串：title、selectedPlan、
confirmedSchedule、packageSummary。每个字段都应简洁、忠实于输入事实。

该 Application 是 DISPLAY_ONLY，不包含 Action，也不等待或暂停。工具成功
返回后，输出一句简短的完成说明；最终活动包以运行时持久化的 Application
卡片为准，使调用方之后通过 read/view 刷新仍可读取。不要把普通模型文本
伪装成卡片，不调用交互 Action，不发布或发送到外部平台。

本 Skill 可以独立使用：调用方直接提供一个已选方案和已确认安排时即可
生成活动包。它不依赖固定 Workflow，不生成路由指令，也不直接访问数据库、
文件或外部系统。
