# v0.4.3 同步宿主 v3.43.0 / UI v0.9.0

2026-11-08 通过 GitHub Releases API 确认最新正式版为 [宿主 v3.43.0](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.43.0)（2026-11-07 19:38 UTC 发布）和 [UI v0.9.0](https://github.com/zyycn/codex-proxy-ui/releases/tag/v0.9.0)（同日 19:12 UTC 发布）。按标签源码对比 [宿主 v3.39.1 → v3.43.0](https://github.com/zyycn/codex-proxy-rs/compare/v3.39.1...v3.43.0) 与 [UI v0.8.0 → v0.9.0](https://github.com/zyycn/codex-proxy-ui/compare/v0.8.0...v0.9.0)，覆盖 SDK、Runtime、打包 CLI、页面桥、主题与模型执行策略；不跟随浮动 `main`。

## 版本与兼容范围

| 对象 | 升级前 | 本次目标 |
| --- | --- | --- |
| SDK / 打包 CLI | v3.39.1，`12c32fcdecb29da4e44a21bb33fbbf2aaf6a166d` | v3.43.0，`402bc37fbb5c83378cc83cec89e9fa251e4a99c1` |
| SDK crate / RPC | `0.1.0` / v7 | 不变 |
| UI 官方 Release 归档 | v0.8.0 | v0.9.0；更新 pnpm 锁文件，不从 Git 源码安装 |
| 插件、后端、前端版本 | v0.4.2 | v0.4.3；自动发布继续追加 UTC 时间戳 |
| 宿主清单范围 | `>=3.37.2, <4.0.0` | 保持；旧宿主补弹层阴影回退 |

Cargo 依赖、锁文件、CI 安装 CLI 与 README 构建命令使用同一固定提交。其余 Rust、前端依赖版本不变。插件身份仍为 `local.model-health`，management v2、maintenance v1、`runs` schemaVersion 1 与 16 槽位不变，不迁移或重算历史。

## SDK：设置字段有破坏性变化，现有回调不受影响

`RuntimeSettings`、`ReplaceRuntimeSettings` 将 `concurrency_wait_timeout_seconds` 替换为 `key_queue_timeout_seconds`、`account_queue_timeout_seconds`，并增加 `switch_account_on_queue_failure: bool`；`From` 转换同步修改。这些类型使用 `deny_unknown_fields`，新字段无反序列化默认值，旧设置 JSON 不能直接交给新类型。

本插件不调用设置服务、不构造这些类型，因此不增加设置转换层，也不修改全局排队或换号策略。实际使用的 `host.auth.list/get_runtime`、`host.keys.list`、`host.models.list`、`host.model.*`、`host.state.*`、`host.http.*` 类型均未变化；握手、GPE2/HME1、挂起/恢复授权和调用预算保持原合同。CLI 仅 README 变化，打包格式与参数不变。

SDK 另新增历史用量快照读取与统计：`host.usage.records.scan`、`host.usage.statistics.query`、`host.usage.read.next/close`，以及 `UsageReader` 和用量错误 `Cancelled/Timeout`。Runtime 增加读取句柄、快照及父调用结束时的回收。这些是独立新增能力，本插件继续使用每题响应中的请求 ID 与用量，不新增历史扫描或权限需求。

依据：[设置合同](https://github.com/zyycn/codex-proxy-rs/blob/402bc37fbb5c83378cc83cec89e9fa251e4a99c1/backend/crates/gateway-plugin/sdk/src/call/services/settings.rs)、[用量读取合同](https://github.com/zyycn/codex-proxy-rs/blob/402bc37fbb5c83378cc83cec89e9fa251e4a99c1/backend/crates/gateway-plugin/sdk/src/call/services/usage/read.rs)、[SDK 用量客户端](https://github.com/zyycn/codex-proxy-rs/blob/402bc37fbb5c83378cc83cec89e9fa251e4a99c1/backend/crates/gateway-plugin/sdk/src/client/usage.rs)。

## 执行策略：保持固定账号与原检测参数

| 上游变化 | 本插件的处理 |
| --- | --- |
| v3.42.0 拆分 Key/账号排队超时；依次排队可能延长总等待；可选队满/超时后换号一次，默认关闭 | 每题仍显式绑定账号、Key、Provider 与协议。OpenAI selector 只有 `required_account().is_none()` 才进入排队失败重选，固定账号不会被此开关替换。单题总预算仍为 120 秒、流读取 90 秒、维护交接余量 150 秒；不因宿主等待更久而放宽 |
| v3.40.0 开始保留 Responses 的 `max_output_tokens` 并交给上游校验；v3.42.0 进一步规范 Codex OAuth 不支持的请求选项 | Meow 继续发送原引擎的短答限制和 reasoning 参数；此前可能被宿主移除的输出上限现会生效，跨宿主版本的回答长度可能变化。截断/失败仍按原解析器处理，不计为有效评分。ModelTrace 继续使用供应商默认采样，不加 Meow 的上限 |
| 模型目录采用账号范围内的模型画像；部分已识别的非文本模型不再进入默认 Agent 列表 | 继续经所选 Key 的 `host.models.list` 读取，不自行拼接目录、不绕过宿主资格判定。可见模型不保证所选账号可用，宿主拒绝后暂停 |
| Key 安装身份改用种子派生；会话亲和、轮次 token 及并发租约回收调整 | 交由宿主原生链路处理。检测题仍为独立请求，`previous_response_id=None`、`store=false`，不持久化轮次 token、不伪造客户端头 |

扩展现有后台错误回归，新增 `timeout / not_sent`，与 `capacity / not_sent`、`upstream / 503 / sent`、`upstream / 503 / ambiguous` 一起验证：只保存一次失败、保留发送状态、错误不评分、无流读取或直连回退、不自动重发，下一排队任务正常完成。

依据：[排队重选的账号约束](https://github.com/zyycn/codex-proxy-rs/blob/402bc37fbb5c83378cc83cec89e9fa251e4a99c1/backend/crates/providers/openai/src/credential/selector.rs)、[上游固定账号排队回归](https://github.com/zyycn/codex-proxy-rs/blob/402bc37fbb5c83378cc83cec89e9fa251e4a99c1/backend/crates/providers/openai/tests/credential/contract/mod.rs)、[请求规范化](https://github.com/zyycn/codex-proxy-rs/blob/402bc37fbb5c83378cc83cec89e9fa251e4a99c1/backend/crates/providers/openai/src/compat/request.rs)、[v3.40.0](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.40.0)、[v3.42.0](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.42.0)。

## 页面：适配 UI v0.9.0，保留旧宿主的弹层阴影

UI 新增场景配色、`default/soft` 材质、卡片渐变与专用弹层阴影，Select/Popover 使用 `popover-shadow` 而非原 `box-shadow`。已用组件、中文 locale、Vite/Tailwind 入口与 `createTheme/applyTheme` 调用保持兼容；新增侧栏不在本插件使用范围内。

宿主继续用无前缀语义 Token 通过管理桥写入 `--z-*` 内联变量，新宿主的材质、尺寸和配色直接生效。旧宿主没有 `popover-shadow`，直接更新 UI 会导致下拉阴影计算为 `none`；本次在生产隔离页复现该失败后，增加一条根级 CSS 默认值：

```css
:root { --z-popover-shadow: var(--z-box-shadow); }
```

新宿主的内联值优先，旧宿主沿用原阴影；缺少卡片背景图时浏览器自然采用 `none`，无需兼容层或复制主题算法。生产页仍由宿主控制主题。

管理桥版本仍为 v2，新增 `openExternal(url)` 需用户点击并在宿主确认 HTTPS 地址。本插件继续使用已有地址展示/复制入口，不新增外链功能，也不因此提高兼容下限。

依据：[UI 主题与组件差异](https://github.com/zyycn/codex-proxy-ui/compare/v0.8.0...v0.9.0)、[宿主主题桥](https://github.com/zyycn/codex-proxy-rs/blob/402bc37fbb5c83378cc83cec89e9fa251e4a99c1/frontend/src/views/plugins/management/bridge-runtime.ts)、[外链确认](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.42.1)。

## 验证记录

环境：Windows、Rust 1.99.1、Node 24.19.0、pnpm 12.14.0、Python 3.13.7 / NumPy 2.5.1、真实 Chrome；不修改系统默认 Node。

| 检查 | 结果 |
| --- | --- |
| `cargo fmt --check --manifest-path backend/Cargo.toml` | 通过 |
| 显式指定 `MODEL_HEALTH_TEST_PYTHON` 后执行 `cargo test --locked --manifest-path backend/Cargo.toml` | 66 项通过；包含后台超时/错误、固定账号、双方法、旧历史、取消恢复、RPC v7 和 Python/Rust 帧交叉验证；文档测试 0 项 |
| `pnpm --dir frontend install --frozen-lockfile`、`test`、`build` | 冻结安装、8 项测试、类型检查及生产构建通过 |
| `python -X utf8 -B -m unittest discover -s scripts/tests -v` | 5 项通过 |
| 浏览器回归 | `scripts/browser-qa.mjs`、`scripts/updates-browser-qa.mjs`：双方法与报告、暂停/继续/结束、搜索、深浅色和窄屏、生产隔离页及复制；扩展隔离页检查柔光深浅主题及移除新增 Token 的旧主题合同，核对渐变、阴影、内联覆盖和无横向溢出 |
| 发布配置 | workflow YAML、双架构矩阵、构建脚本与全部 workflow Bash 语法、实际生成的 Release 说明、`git diff --check` 通过；SDK/CLI/锁文件同源及版本一致性由 Rust 合同测试核对 |

已查看生产隔离页柔光浅色、柔光深色和旧 Token 合同窄屏截图，位于本地忽略目录 `review/screenshots/sdk-theme-*.png`。旧 Token 检查模拟合同形状，未重新安装旧宿主；旧宿主合同依据同时包括标签差异与 [v3.37.2 适配记录](sdk-upgrade-2026-11-01.md)。

本机无 Docker；Linux 双架构内嵌引擎构建、CLI 打包和受限容器冒烟由推送后的 release workflow 执行，以对应 Actions 结果为准。未安装真实宿主或调用计费模型；真实检测仍由使用者主动触发。

## 更新与回退

更新同一 `local.model-health`，保留私有状态，不卸载重装。v0.4.2 与 v0.4.3 使用相同数据和协议，可在兼容宿主上切回旧插件制品；升级前保留旧包和宿主数据备份。

宿主升级另有独立约束：v3.40.0 的 CPR Link 只接受 v3 快照，互联两端需协调升级；宿主数据库包含 `0038` 及后续排队设置迁移，源码部署若运行过中间版 `0039_queue_timeouts.sql`，须按 v3.42.0 发布说明在独立数据库验证。插件数据不迁移不代表宿主数据库可直接回退。插件制品仍仅支持 Linux glibc x86_64/ARM64。
