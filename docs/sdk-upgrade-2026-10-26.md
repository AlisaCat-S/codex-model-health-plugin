# v0.3.0 对应宿主 v3.33.0：升级到 RPC v7

插件从 v0.2.2 升至 **v0.3.0**，SDK 与打包 CLI 同步到 **Codex Proxy RS v3.33.0**，UI 同步到 **v0.7.0**。宿主 v3.33.0 仅接受 RPC v7；旧版插件必须重新构建打包后更新，不能只改清单。

## 固定正式版与真实提交

2026-10-26 查询上游 GitHub 最新正式 Release，并对比固定版本的 SDK、Runtime、CLI 和 UI 源码：

| 依赖 | 升级前 | 当前目标 |
| --- | --- | --- |
| `gateway-plugin-sdk` / `cpr-plugin` | 宿主 v3.31.1，`06e1d8f0ac33d8633198d837c4f9017ad466f358`，RPC v5 | [宿主 v3.33.0](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.33.0)，`8c8618aa0f841638262262e3338c115bc075f125`，RPC v7 |
| `@codex-proxy/ui` | v0.6.1 官方 Release 包 | [v0.7.0](https://github.com/zyycn/codex-proxy-ui/releases/tag/v0.7.0) 官方 Release 包 |
| 插件版本 | v0.2.2 | v0.3.0；自动发布继续附加 UTC 时间戳 |
| 宿主清单范围 | `>=3.31.1, <4.0.0` | `>=3.33.0, <4.0.0` |

SDK crate 版本仍为 `0.1.0`，应以宿主提交和协议版本识别合同。v3.33.0 是附注标签，标签对象为 `40604cf05bd336d09376c5596f3b2112aaa6bc6a`，实际提交为上述 `8c8618aa…`；Cargo、锁文件和 CLI 均固定实际提交。

对比：[宿主 v3.31.1…v3.33.0](https://github.com/zyycn/codex-proxy-rs/compare/v3.31.1...v3.33.0)、[UI v0.6.1…v0.7.0](https://github.com/zyycn/codex-proxy-ui/compare/v0.6.1...v0.7.0)。

## RPC v6 的预算与 v7 的协作调度都要适配

本仓库升级前仍使用 RPC v5，比宿主发布说明中提到的 v6 更早。此次同时跨过两个合同变更：

| 边界 | 上游差异 | 本插件采用的处理 |
| --- | --- | --- |
| RPC v6 调用预算 | `Ready` 新增必填 `call_budgets`；移除 `SessionConfig.maximum_call_timeout`，改为分阶段预算；支持 `set_call_budgets` 和 `remaining_budget` | 沿用 SDK `PluginSession::accept/run` 和默认会话配置，由 SDK 发送 `call_budgets={}`；management 默认仍为 120 秒，每次只执行一题，保留现有模型流读取 90 秒上限，不声明整轮后台任务预算 |
| RPC v7 调度 | 父 future 返回 Pending 时发送 `Suspend` 归还执行名额；唤醒后发 `Resume`，收到宿主 `Resumed` 才能继续，epoch 从 1 严格递增 | 生产执行交给新版 SDK，不自建调度器；Rust 测试宿主和 Python 安装包冒烟宿主均处理并校验挂起、恢复授权与 epoch，不能再只等待 Callback/Result |
| 回调驻留与回收 | 回调结果到达不再代表释放额度；`CallbackConsumed { id, parent_id }` 表示消费或 future 被丢弃；默认回调容量 64 → 320，统一包含 `next`，最大 512 | 保留 SDK 默认值和串行模型执行；测试宿主跟踪驻留回调，最终结果前确认回收，不自动重试可能已发出的业务操作 |
| 处理预算计时 | 普通模型/HTTP 回调及恢复排队仍计时；仅父任务挂起且驻留回调全部为 `next` 时暂停预算 | 本插件没有 `next` 中间件，不把模型网络等待当成免费预算，不延长既有请求时限 |
| 帧与安装包 | RPC 版本从 5 经 6 升至 7；帧仍为大端 u32 元数据长度 + u64 载荷长度，业务 JSON 与正文分段；调度控制帧无载荷 | 使用同源 CLI 生成 `package.protocolVersion=7`；Python 帧编码抽为 `scripts/rpc_fixture.py`，固定样本与真实 Rust SDK 交叉验证 |

依据：[预算变更](https://github.com/zyycn/codex-proxy-rs/commit/0a87ac7)、[调度变更](https://github.com/zyycn/codex-proxy-rs/commit/614c81c)、[SDK 会话合同](https://github.com/zyycn/codex-proxy-rs/blob/8c8618aa0f841638262262e3338c115bc075f125/backend/crates/gateway-plugin/sdk/README.md)、[宿主兼容声明](https://github.com/zyycn/codex-proxy-rs/blob/8c8618aa0f841638262262e3338c115bc075f125/backend/crates/gateway-plugin/runtime/plugin-host-compatibility.json)。

## 身份查询与模型执行分离，不增加新的请求链

v3.33.0 将客户端身份、账号授权、模型目录查询与模型执行准入分开。同一父调用内的 `host.models.list`、授权检查和显式 Key 执行共享冻结身份及权限快照，目录查询不再建立模型执行图。实际模型执行仍由 Core 检查健康、冷却、额度和租约。

本插件现有 `host.auth.list/get_runtime`、`host.keys.list`、`host.models.list`、`host.model.execute_stream/stream_read/stream_close` 的请求与响应类型未发生破坏性变更，继续使用原有入口。模型请求仍显式绑定账号 ID、Key ID、`provider=openai`、`protocol=openai`，不读取密钥、不绕开宿主代理和计费。

新增的客户端认证、账号/模型权限查询、完整额度事实和账号代理 HTTP 是独立能力：`verify_client`、`check_access`、`quota_details`、`account_http`。本插件不需要新增认证入口或自发账号 HTTP，不为此次升级增加这些调用，也不以授权查询替代实际执行准入。

清单仍为 v2，management 能力和页面桥仍为 v2，GPE2/HME1 与原生 SSE/WebSocket 封套未变。v3.33.0 修复 WS 错误转 SSE 时的 Retry-After 透传；插件继续把原始事件交给解析器，错误不参与评分，不引入自动重试。

依据：[能力与回调合同](https://github.com/zyycn/codex-proxy-rs/blob/8c8618aa0f841638262262e3338c115bc075f125/backend/crates/gateway-plugin/sdk/docs/capabilities.md)、[宿主模型回调](https://github.com/zyycn/codex-proxy-rs/blob/8c8618aa0f841638262262e3338c115bc075f125/backend/crates/gateway-plugin/runtime/src/callback/model.rs)。

## UI v0.7.0 的破坏性变更不涉及本页表单调用

v0.7.0 的 `Form.validate/validateField` 无回调时，校验失败改为 reject；自定义 `validator` 改为 `(rule, value, callback, source, options)`，异步校验使用 `asyncValidator`。本页使用业务状态和管理接口校验，没有调用 `ZForm`、这些校验方法或自定义 validator，不需要引入 catch 或改写校验器。

实际使用的 ZButton/ZCard/ZSelect/ZSegmented/ZTable/ZTag/ZIconButton、简体中文 locale、主题和 Vite 入口继续可用。表格默认单元格内边距由 16px 降到 12px，单行省略、焦点和浮层行为也有修复；通过实际浏览器验证搜索、历史表格、浅深色、窄屏及隔离页面，而不只依赖类型检查。

依据：[UI v0.7.0 发布说明](https://github.com/zyycn/codex-proxy-ui/releases/tag/v0.7.0)、[表格变化](https://github.com/zyycn/codex-proxy-ui/compare/v0.6.1...v0.7.0)。

## 升级、发布与回退

升级先准备 v3.33.0 宿主和本版重新构建的插件包，再更新同一 `local.model-health` 插件。保留旧宿主与插件制品及宿主数据备份；3.32.x 及更早宿主继续使用匹配的旧插件。v3.33.0 上不能直接回退到 RPC v5/v6 插件，回退旧协议时须同时恢复匹配的旧宿主。

`runs` schema 仍为 v1，插件身份、16 个历史槽位、算法、冻结题目/基线和旧 Meow 记录读取方式保持不变，无需迁移私有检测数据。自动 Release 说明标明“对应宿主 v3.33.0 / RPC v7”、清单范围和本分析的提交链接，避免仅凭插件版本选错宿主。

## 验证证据

本地通过：51 项 Rust 测试、6 项前端单测、5 项 Python 夹具单测、前端冻结安装和生产构建、两套浏览器验收，以及 workflow YAML、Shell 语法和实际生成的发布说明检查。

- Rust 协议回归覆盖两种检测、固定账号/Key、历史、暂停续测、流 EOF 和错误回收，同时逐帧核对 v7 调度和驻留消费。新增未授权禁止推进、取消后迟到授权不复活及旧 v5/v6 握手拒绝测试。
- Python 冒烟帧样本通过锁定 Rust SDK 解码/重编码；单测检查帧分段、输入不被修改、epoch 和驻留消费，并拒绝错误控制帧及提前返回结果。
- 前端冻结锁文件安装、单测、类型检查和生产构建，以及两套浏览器验收通过；实际查看浅色、深色和窄屏截图，未见布局或裁切问题。浏览器证据在本地 `review/`（忽略目录）。

本机为 Windows，没有 Docker；Linux x86_64/ARM64 内嵌引擎安装包和受限容器验收由推送后触发的 release workflow 执行。本次本地验证不发送真实计费模型请求、不安装到运行中的宿主。
