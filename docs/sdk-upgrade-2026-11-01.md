# v0.4.0 适配宿主 v3.37.2 与 UI v0.8.0

2026-11-01 查询上游最新正式 Release，选择固定版本而非浮动 `main`。本次对比 v3.33.0 → v3.37.2 的 SDK、Runtime 回调、CLI、宿主页面主题桥，以及 UI v0.7.0 → v0.8.0 的源码和发布说明。

## 固定版本与兼容范围

| 对象 | 升级前 | 本次目标 |
| --- | --- | --- |
| 宿主 SDK / 打包 CLI | v3.33.0，`8c8618aa0f841638262262e3338c115bc075f125` | [v3.37.2](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.37.2)，实际提交 `641f43b3030b1c68961e05d525e58ec6f4264a15` |
| UI 官方 Release 包 | v0.7.0 | [v0.8.0](https://github.com/zyycn/codex-proxy-ui/releases/tag/v0.8.0) |
| 插件版本 | v0.3.0 | v0.4.0；自动发布继续追加 UTC 时间戳 |
| 宿主范围 | `>=3.33.0, <4.0.0` | `>=3.37.2, <4.0.0` |

SDK crate 版本仍为 `0.1.0`，RPC 仍为 **v7**。Cargo、锁文件和发布 workflow 的 CLI 固定同一实际提交；前端保留官方预构建归档和冻结锁文件，不执行 UI 仓库的构建脚本。

对比：[宿主源码](https://github.com/zyycn/codex-proxy-rs/compare/v3.33.0...v3.37.2)、[UI 源码](https://github.com/zyycn/codex-proxy-ui/compare/v0.7.0...v0.8.0)。

## SDK 差异：现有调用继续使用，未声明的能力不扩展

| 合同 | 上游变化 | 对本插件的影响与处理 |
| --- | --- | --- |
| 会话、帧、预算 | RPC v7、挂起/恢复授权、回调消费、GPE2/HME1 未变 | 继续使用 `PluginSession`；保留 1 小时维护预算、单题 120 秒、流读取 90 秒和回收测试，不复制调度逻辑 |
| 已声明能力 | management v2、maintenance v1 未变 | 清单能力和页面桥版本保持不变 |
| 模型目录 | `model_catalog` v1 → v2，改为 `ModelCatalogRegistrationV2 { aliases, models }` 和 `MODEL_CATALOG_REGISTER_V2`；新增适配模型画像，`reasoning_summary` 默认 false | 插件不贡献模型目录，只查询 `host.models.list`，无需注册目录或声明推理摘要能力 |
| 设置服务 | 原自动冻结字段合并为 `account_error_protection` 及规则结构 | 插件不读写全局运行设置，无调用者需要迁移；不新增设置回调 |
| 上游适配器 | `UpstreamFailure` 增加可选 `error_type` | 插件不实现适配器，现有模型流消费合同不变 |
| 宿主错误 | 明确的上游预算耗尽映射为 `ErrorCode::Capacity`；部分消息标点统一 | 沿用错误暂停、记录请求关联和人工续测，不依赖错误文案做业务判断，不增加自动重试 |
| 安装兼容检查 | 版本范围或能力不匹配不再自动启动；管理员风险确认仅适用于本次启动 | 将最低宿主定为本次适配和验证的 v3.37.2；不依赖强行启动绕过兼容范围 |

`host.auth.list/get_runtime`、`host.keys.list`、`host.models.list`、`host.model.execute_stream/stream_read/stream_close` 与私有状态合同未发生破坏性变化。账号 ID、Key ID、`provider=openai`、`protocol=openai` 的显式绑定继续生效，代理、授权、配额和计费仍由宿主负责。

宿主新增 Chat Completions 入口和 CPR 互联不要求本插件新增网络路径：检测继续提交原生 Responses 请求，经宿主处理。受管适配器的 HTTP 429 重放资格变化不属于本插件的管理/维护模型调用，不据此增加检测重发。

依据：[SDK 合同](https://github.com/zyycn/codex-proxy-rs/tree/641f43b3030b1c68961e05d525e58ec6f4264a15/backend/crates/gateway-plugin/sdk)、[宿主兼容清单](https://github.com/zyycn/codex-proxy-rs/blob/641f43b3030b1c68961e05d525e58ec6f4264a15/backend/crates/gateway-plugin/runtime/plugin-host-compatibility.json)、[安装与启动规则](https://github.com/zyycn/codex-proxy-rs/blob/641f43b3030b1c68961e05d525e58ec6f4264a15/docs/plugins.md)。

## UI 差异：迁移主题命名空间与公开 API

UI v0.8.0 删除旧 `cp` 别名，默认 CSS 变量、组件 DOM 类名和 utility 类名统一为 `z`。宿主主题桥也改为传递无前缀语义 Token，再写为 `--z-*`。因此仅升级依赖会让旧自定义样式和字体/颜色工具类失效，即使 RPC 握手正常。

- `App.vue` 的 `text-cp-*` 改为 `text-z-*`；全局样式、来源组件和模拟页中的 `--cp-*` 改为 `--z-*`
- 焦点轮廓使用实际 Token `--z-control-outline`，等宽字体使用宿主桥提供的 `--z-font-family-code`，不继续引用不存在的旧 Token
- 模拟页将已移除的 `applyResolvedTheme/resolveTheme` 和大写默认常量替换为 `applyTheme(root, createTheme({ scheme }))`；生产页仍由宿主应用主题，不覆盖用户主题
- 浏览器夹具同步 `z-runtime-theme`，生产隔离页按新版宿主桥的语义 Token 方式写入 `--z-*`，不注入 `cp` 兼容层
- 新增小型主题回归测试：逐个核对本页引用的变量是否来自当前 UI Token 或宿主字体扩展，避免改完前缀后仍有无效变量

已使用的组件导出、中文 locale、Vite 插件和 Tailwind 入口继续可用。表单错误动画、展开行动画、Popover/Select 过渡与 Markdown 提示块由组件库提供，不新增本页功能或重排布局；本页不使用 `ZForm` 校验器，无需改造校验流程。

依据：[UI 发布说明](https://github.com/zyycn/codex-proxy-ui/releases/tag/v0.8.0)、[主题公开 API](https://github.com/zyycn/codex-proxy-ui/blob/v0.8.0/src/theme/index.ts)、[宿主主题采集](https://github.com/zyycn/codex-proxy-rs/blob/641f43b3030b1c68961e05d525e58ec6f4264a15/frontend/src/views/plugins/management/frame.ts)、[主题桥应用](https://github.com/zyycn/codex-proxy-rs/blob/641f43b3030b1c68961e05d525e58ec6f4264a15/frontend/src/views/plugins/management/bridge-runtime.ts)。

## 升级与回退保留检测历史

先准备 v3.37.2 宿主和重新构建的本版插件包，再更新同一 `local.model-health` 插件。插件身份、`runs` schemaVersion 1、16 个历史槽位、Meow/ModelTrace 原算法、冻结题目与基线均保持不变，无需迁移私有检测数据。

旧宿主继续使用匹配的旧插件；旧插件与新宿主即使都使用 RPC v7，也可能因主题桥不同而显示异常。保留升级前宿主、插件制品及宿主数据备份，回退时同时核对协议和主题桥；不通过卸载重装清除历史。

## 验证范围

本地使用 Rust 1.99.1、Node 24.19.0、pnpm 12.14.0、Python 3.13 / NumPy 2.5.1 和真实 Chrome，以下检查通过：

| 检查 | 命令与结果 |
| --- | --- |
| Rust / SDK 协议 | 显式设置 `MODEL_HEALTH_TEST_PYTHON=C:/Python313/python.exe`；`cargo test --locked --manifest-path backend/Cargo.toml` 覆盖的 62 项测试通过，包括双方法、账号/Key 绑定、历史、后台队列、取消恢复、EOF、错误回收、RPC v7 调度和版本合同；文档测试通过（0 项） |
| 前端依赖与构建 | `pnpm --dir frontend install --frozen-lockfile`、`pnpm --dir frontend test`（8 项）、`pnpm --dir frontend build`（含类型检查）通过 |
| Python 帧夹具 | `python -X utf8 -B -m unittest discover -s scripts/tests -v`，5 项通过，固定帧继续与新 Rust SDK 交叉验证 |
| 浏览器交互 | `scripts/browser-qa.mjs`、`scripts/updates-browser-qa.mjs`、`scripts/recovery-browser-qa.mjs`、`scripts/background-browser-qa.mjs` 全部通过；覆盖双方法、搜索、暂停/继续/结束、旧历史、页面关闭后的后台进度、断线恢复、异常记录和隔离页复制；页面异常为 0 |
| 实际外观 | 查看浅色设置、深色报告、390px 窄屏报告和生产隔离页截图，主题生效且无横向溢出；截图位于本地忽略目录 `review/screenshots/` |
| 发布配置 | workflow YAML 解析、构建脚本及 Release 说明脚本的 Bash 语法检查、实际生成的 Release 说明均通过；SDK / CLI / 锁文件提交一致性由 Rust 测试检查 |

本机为 Windows、没有 Docker；Linux x86_64/ARM64 内嵌引擎构建、安装包和受限容器验收由推送后的 release workflow 执行。真实宿主安装与计费模型检测仍由用户主动触发。
