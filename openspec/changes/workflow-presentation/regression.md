# Workflow 展示分层联调记录

日期：2026-10-07。环境：公网 PRT，正常管理员登录。

## 已通过

- TypeScript 和 Vite build；参数/结果分块、Unicode、凭据脱敏、同步异步观测与原异常保持的定向探针。
- 新运行 `eeaab23c91384944a4fed8822fd05192`：首节点真实模型/RPC 出卡，实际勾选两条阅读要点并确认，首节点成功并推进第二节点。
- 新工具详情展示真实参数、完整结果、耗时；复制显示“已复制”。浏览器虚拟剪贴板不能证明系统粘贴内容，仅验证页面反馈。
- 刷新后恢复“执行过程 → 业务卡片 → 后续执行过程 → 助手说明”，无手动重新读取入口。
- 旧完成运行三节点卡片恢复、只读控件、中文业务标题及技术信息折叠；旧未采集参数/结果明确标注缺失。
- Chat 人员卡片恢复第二页、保留选择，无新消息或操作重放。
- 390px 窄屏 document.scrollWidth=clientWidth=390，无横向溢出；viewport 已恢复。浏览器 error/warn 为空。

## 发现与限制

- 第二节点 content.artifact.get 抛 RPC_EXECUTION_FAILED 后仍显示执行中。同身份同一只读查询再次诊断成功，原始故障原因不明；不重放 Action。
- 续跑异常收敛已修复并随 433bfb1 部署：真实异常持久化 FAILED，活动节点标记 UNCONFIRMED，阻止新执行；保留成功 Action 和前置节点。隔离探针覆盖终态读回、准入、GraphInterrupt 排除、原异常保留和终态防覆盖。
- 原联调 run 经既有 stop 接口明确结束，页面回读已停止，未改写原始错误记录。未重放该 Action；本轮完整新三节点成功链路仍未通过，不能标记全部业务准出。
- 模型过程仍可能英文，未伪造翻译或改写历史。最终说明与引擎成功状态分开。
- 未覆盖全站手机布局；未变更业务卡片合同、定时配置及外部发布能力。

## 部署

- 集成代码：433bfb17012bdef8656efd45e237b81cf4348766，origin/main 与 GitHub/main 同步。
- Runtime：a2flow-realchat:workflow-ui-433bfb1，仅叠加本轮观测、卡片关联和失败终态文件。
- B 服务镜像未修改，仅替换 employee 静态目录为 workflow-ui-433bfb1，入口 index-BEn46RqA.js。
- Java、内容业务、RPC 执行服务、账号、Redis、scheduler 和 PostgreSQL 未重建；保留旧镜像及私有部署配置以回退。
