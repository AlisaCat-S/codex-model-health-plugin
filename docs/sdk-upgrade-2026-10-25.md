# SDK v3.31.1 适配：RPC 版本相同不等于字段兼容

当前源码已将 SDK 与打包 CLI 从宿主 v3.30.2 同步到 **v3.31.1**，UI 从 v0.3.2 同步到 **v0.6.1**。新构建应安装到 **3.31.1+** 宿主；旧宿主保留升级前的插件制品。插件身份、私有状态 schema、检测算法与冻结基线保持不变。

## 固定正式版本，不跟随浮动 main

2026-10-25 查询上游 GitHub Release，并直接比较固定提交的 SDK、Runtime、Provider、CLI 与 UI 源码：

| 依赖 | 升级前 | 当前固定目标 |
| --- | --- | --- |
| `gateway-plugin-sdk` / `cpr-plugin` | v3.30.2，`76291f448cdf1d1da2027da32b7c949deb998c7a` | [v3.31.1](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.31.1)，`06e1d8f0ac33d8633198d837c4f9017ad466f358` |
| `@codex-proxy/ui` | v0.3.2，Git 源码包 | [v0.6.1](https://github.com/zyycn/codex-proxy-ui/releases/tag/v0.6.1)，官方预构建 `.tgz` |

SDK crate 自身的版本仍是 `0.1.0`，因此不能只比较 Cargo 包版本。`backend/Cargo.toml`、`Cargo.lock` 与发布 workflow 的 CLI 使用同一个完整宿主 revision；前端锁文件固定 Release URL 和包完整性。检查时的宿主 main `84c0db26135dae694a5f5ac608ed6c04df049234` 与 v3.31.1 的 SDK、CLI 无差异，选择正式版便于复现。

对比依据：[宿主差异](https://github.com/zyycn/codex-proxy-rs/compare/76291f448cdf1d1da2027da32b7c949deb998c7a...06e1d8f0ac33d8633198d837c4f9017ad466f358)、[UI 差异](https://github.com/zyycn/codex-proxy-ui/compare/v0.3.2...v0.6.1)。

## 1. 观测字段删除会让旧宿主的整个事件解码失败

v3.31.1 删除 `ResponseObservation.upstream_response_model` 和 `RequestCompleted.response_model`。前者位于插件实际读取的 `host.model.stream_read` 事件中；SDK 的 `ResponseObservation` 使用 `deny_unknown_fields`。

v3.30.2 的 Runtime 会发送 `upstream_response_model`，即使值为 `null` 也不省略。新版 SDK 因这个未知字段拒绝整个 GPE2 事件，而不只是忽略一项未使用信息。插件虽然没有直接读取模型观测字段，也会受影响。这是将 `plugin.json` 下限从 `3.29.7` 调整为 **`3.31.1`** 的直接原因，不能保留原范围并宣称兼容。

选择与正式宿主匹配的严格 SDK 解码，不在插件里复制或宽松改写二进制协议。旧宿主升级到 3.31.1 后再切换新插件；宿主将兼容范围作为风险提示，使用者不应绕过此提示强行启用。回退宿主时同时保留匹配的旧插件制品与私有状态备份。

删除的是宿主的观测与请求记录字段，原始 SSE / WebSocket 中的 `response.model` 仍透传。插件继续根据原始回答做行为指纹评分，不把响应自报模型当作身份依据。原始 SSE、WS JSON、拒答、错误、截断和读到独立 EOF 后才评分的处理沿用现有实现。

依据：[SDK 观测类型](https://github.com/zyycn/codex-proxy-rs/blob/06e1d8f0ac33d8633198d837c4f9017ad466f358/backend/crates/gateway-plugin/sdk/src/call/model/facts.rs)、[旧 Runtime 投影](https://github.com/zyycn/codex-proxy-rs/blob/76291f448cdf1d1da2027da32b7c949deb998c7a/backend/crates/gateway-plugin/runtime/src/callback/facts.rs)、[移除模型观测的提交](https://github.com/zyycn/codex-proxy-rs/commit/3f6607209b0a5ce4b4a98e51e32115b4ef6e998d)。

## 2. 新能力合同不等于本插件需要增加能力

| 边界 | 上游变化 | 本插件处理 |
| --- | --- | --- |
| 进程 RPC / 清单 | 仍为 v5 / v2 | 不改握手和帧编码 |
| `management` | 仍为 v2，页面桥仍为 v2 | 保留路由、资源、管理桥与调用入口 |
| `middleware` | v5 → v6，新增 `outbound` 准备阶段 | 本插件未声明中间件，不增加挂载或请求改写 |
| `upstream_adapter` | v4 → v5，注册项必须有 `account_ids` | 本插件不注册适配器，无需填写新字段；模型请求仍显式绑定账号和 Key |
| 模型流 | GPE2 / HME1 与 `WirePayload` 变体未变，观测字段有上述删除 | 继续使用 SDK 编解码及现有穷尽匹配，不强制 HTTP、不绕开原生请求链 |

v3.31.0 曾新增的 `provider_parameters` / `installation_id` 专用构造入口已在 v3.31.1 移除，不应为了“适配新版”引入这个过渡接口。宿主配置的模型映射、中间件和适配器仍可能影响检测结果，原有报告说明继续适用。

v3.31.0 还将 Key 费用落库改为后台批量结算：用量界面金额可能稍后更新，不能用请求结束瞬间金额未变判断漏计。插件保持请求 ID、账号 ID、Key ID 的证据链与保守尝试计数，不增加自动重试或自行扣费。

依据：[v3.31.0 说明](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.31.0)、[v3.31.1 清单合同](https://github.com/zyycn/codex-proxy-rs/blob/06e1d8f0ac33d8633198d837c4f9017ad466f358/backend/crates/gateway-plugin/sdk/docs/manifest.md)、[能力与管理桥合同](https://github.com/zyycn/codex-proxy-rs/blob/06e1d8f0ac33d8633198d837c4f9017ad466f358/backend/crates/gateway-plugin/sdk/docs/capabilities.md)。

## 3. UI 需要迁移属性语义，不只替换组件名

| 旧接口 | v0.6.1 接口与实际适配 |
| --- | --- |
| `BaseButton` 等 `Base*` 导出 | `ZButton`、`ZCard`、`ZSelect`、`ZSegmented`、`ZTable`、`ZTag`、`ZIconButton` |
| 按钮 `variant="primary"` / `"ghost"` | `type="primary"` / `variant="text"`；新 `variant` 表示表面样式，不再表示语义颜色 |
| `size="sm"` | `size="small"` |
| 图标按钮、分段选择的 `label` | `aria-label`，保留控件可访问名称 |
| Select `searchable` | `filterable`，账号、Key、请求模型仍可搜索 |
| Table `rows` / 列 `format` / `BaseTableColumn` | `data` / `formatter` / `TableColumn`；保留历史时间、方法与档位格式化及自定义单元格 |
| 组件默认文案 | 新库默认英文，使用 `ZConfigProvider` + `zhHans` 保持搜索、空结果及加载提示为简体中文 |
| Git 安装源码并允许构建脚本 | 官方固定 Release `.tgz`；移除旧 Git 包的 `allowBuilds` 授权 |

`styles.css`、`tailwind.css`、主题入口和 Vite 适配器保持原有公开入口。Lucide 的版本约束同步到新 UI 的要求，锁文件统一解析图标依赖。

依据：[v0.6.1 按钮](https://github.com/zyycn/codex-proxy-ui/blob/v0.6.1/src/components/button/types.ts)、[Select](https://github.com/zyycn/codex-proxy-ui/blob/v0.6.1/src/components/select/types.ts)、[Table](https://github.com/zyycn/codex-proxy-ui/blob/v0.6.1/src/components/table/types.ts)、[国际化](https://github.com/zyycn/codex-proxy-ui/blob/v0.6.1/playground/guide/i18n.md)。

## 验证与发布边界

- `backend/tests/sdk_compatibility.rs`：锁定 SDK / CLI revision 一致性；验证 RPC v5、management v2、状态 schema v1；直接复现旧观测字段为 `null` 或字符串时均不兼容，并验证清单范围排除旧宿主。
- `backend/tests/support/stream.rs`：新增成功路径的独立观测帧 + SSE / WS + 独立 EOF 回归；保留原生回答和用量，观测中的私密字段不进入报告。既有协议测试继续覆盖两种检测、旧 Meow 历史、账号身份、暂停续测、错误不评分和失败后释放流。
- `scripts/browser-qa.mjs`：新增历史表格格式化、账号 / Key / 模型搜索和中文无匹配提示断言；既有双方法、浅深色、窄屏、报告隔离、任务操作和历史交互继续验收。
- `scripts/updates-browser-qa.mjs`：覆盖更新检查状态、失败隔离，以及生产 IIFE 在 `sandbox="allow-scripts"` 与宿主 CSP 下的资源、复制地址和管理桥访问。

验证结果：46 项 Rust 测试、6 项前端单测、2 项 Python 夹具测试、冻结锁文件安装、前端类型检查与生产构建均通过。两套浏览器验收通过，页面无脚本异常或横向溢出；已检查浅色、深色及窄屏实际截图。浏览器结果保存在本地 `review/BROWSER-QA.txt`、`review/UPDATES-BROWSER-QA.txt`，截图在 `review/screenshots/`（忽略目录）。

本机环境为 Windows x86_64、Rust 1.99.1、Node 24.19.0、pnpm 12.14.0、Python 3.13 / NumPy 2.5.1。Linux 双架构安装包仍由既有 Docker / CI 路径构建验收；本机没有 Docker，未执行安装包构建或真实宿主端到端，也未发布、安装或发送计费模型请求。发布前由维护者运行既有 release workflow 的 `dry_run`，验收两个架构的安装包。
