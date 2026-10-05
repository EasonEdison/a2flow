# 人员选择 PRT authoring

本目录通过 M 正式 authoring/release 接口独立创建并发布以下资产：

- Capability：`content.people.list` → `ContentService/ListPeople`。
- Capability：`content.people.resolve` → `ContentService/ResolvePeople`。
- A2UI Application：`people-selector`。
- Skill：`people-selection`。

它只复用已存在且已发布到 PRT 的 `a2flow.digital-employee.pc.v1` Catalog，不创建、更新或重新发布 Catalog，也不触碰 `deploy/reading_content` 的资产。不会直写数据库或发布 ONLINE。

## 交互合同

- Application 使用 `DISPLAY_ONLY`：它是不阻塞 Skill/Workflow 完成的展示卡，仍允许用户显式翻页、选择和回填；回填不代表完成 Workflow，也不自动发送消息。
- 首屏 LoadBinding 固定请求 `page=1,pageSize=5`；上一页和下一页 ActionBinding 调用相同真实 RPC。
- `PAGINATION_STATE` 根据响应 `total` 动态计算页数。`total` 是 protobuf `uint64`，ProtoJSON 中为十进制字符串。
- `ARRAY_OBJECT_TO_OPTIONS` 将当前页人员投影为官方 ChoicePicker options。每项 checkbox 的同一个 label 展示姓名、脱敏电话、性别、年龄和爱好；爱好数组用 `、` 连接。
- ChoicePicker 的 value 保存完整 `selectedPersonIds`。翻页 Action 把完整数组放入 action context，并由 ResultAdapter echo 回新 snapshot；不增加人员专属 renderer 或选择归并逻辑。
- 最终按钮只提交 personId 给 `ResolvePeople`。成功响应中的权威姓名和脱敏电话通过一次性 `COMPOSER_DRAFT/APPEND` effect 追加到当前聊天原稿，不自动发送；GET 不持久、不重放。
- 空选择、首页上一页和末页下一页都通过 official Checkable 校验使 Button disabled。失败会显示错误，不伪装空结果或成功。

## descriptor

`content-descriptor.txt` 必须由同一待发布源码提交生成，不能手写：

```sh
PYTHON_BIN=/path/to/python \
PATH="/path/to/venv/bin:$PATH" \
DESCRIPTOR_OUTPUT=/absolute/path/content.pb \
packages/rpc-contracts/scripts/generate-content.sh
base64 < /absolute/path/content.pb | tr -d '\n' > deploy/people_selection/content-descriptor.txt
```

离线测试会确认 descriptor 同时包含 `ListPeople` 和 `ResolvePeople`。

## 浏览器导入

将本目录作为 M 同源静态文件提供，管理员登录后打开 `import.html`。页面只在用户勾选审核并点击按钮后执行。需要填写：

- `RPC targetKey`：默认 `content`。
- 专员 ID：与 M 当前受控配置一致，例如 `101`。
- descriptor：点击页面按钮加载本目录文件，或粘贴/上传同一 base64 文本。

## 隔离 CLI

```sh
M_REVIEW_CONFIRM=people-selection-prt-v1 \
M_FRESH_TEST_DB=1 \
M_ORIGIN=http://127.0.0.1:18080 \
M_SESSION_COOKIE='a2flow_management_session=...' \
RPC_DESCRIPTOR_FILE=/secure/path/content-descriptor.base64 \
RPC_TARGET_KEY=content \
M_SPECIALIST_IDS=101 \
OUTPUT_FILE=/secure/path/people-selection-prt-manifest.json \
node deploy/people_selection/author-prt.mjs
```

离线检查不会发 HTTP：

```sh
node deploy/people_selection/author-prt.mjs --check
node deploy/people_selection/test-assets.mjs
node deploy/people_selection/test-sdk.mjs apps/digital-employee/web
```
