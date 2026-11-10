# v0.4.4 同步宿主 v3.44.0 / UI v0.9.1

2026-11-11（日本时间）通过 GitHub Releases API 确认最新正式版为 [宿主 v3.44.0](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.44.0)（2026-11-09 04:32 UTC 发布）和 [UI v0.9.1](https://github.com/zyycn/codex-proxy-ui/releases/tag/v0.9.1)（同日 04:13 UTC 发布）。本次按正式标签对比 [宿主 v3.43.0 → v3.44.0](https://github.com/zyycn/codex-proxy-rs/compare/v3.43.0...v3.44.0) 与 [UI v0.9.0 → v0.9.1](https://github.com/zyycn/codex-proxy-ui/compare/v0.9.0...v0.9.1)，不跟随浮动 `main`。

## 版本与兼容范围

| 对象 | 升级前 | 本次目标 |
| --- | --- | --- |
| SDK / 打包 CLI | v3.43.0，`402bc37fbb5c83378cc83cec89e9fa251e4a99c1` | v3.44.0，`c622f085748f812936a7371fcc85d1621fa72ca8` |
| SDK crate / RPC | `0.1.0` / v7 | 不变 |
| UI 官方 Release 归档 | v0.9.0 | v0.9.1 |
| 插件、后端、前端版本 | v0.4.3 | v0.4.4；自动发布继续追加 UTC 时间戳 |
| 宿主清单范围 | `>=3.37.2, <4.0.0` | 保持 |

Cargo 依赖与锁文件、CI 安装 CLI、构建文档使用同一固定提交；UI 只更新官方预构建归档与 pnpm 锁文件。其他依赖锁定版本不变。插件身份 `local.model-health`、management v2、maintenance v1、`runs` schemaVersion 1 和 16 槽位均不变，不迁移或重算历史。

## SDK：仅新增代理接口，保留现有网络路径

SDK 的实现差异仅位于 `call/host.rs`、`client/http.rs`：

- `host.proxies.list` / `HostClient::list_proxies`：分页查询代理摘要 `{id, name, enabled}`，不返回连接地址或凭据。请求与结果使用二进制 JSON 载荷，控制元数据为 `{}`。页码从 1 开始，页大小 1–200，搜索最长 256 字节且禁止控制字符。
- `host.http.proxy` / `HostClient::proxy_http`：按代理 ID 在发送时读取当前配置，不依赖账号，不注入账号认证；代理不存在、禁用或连接失败时不回退直连。响应仍使用既有 `HostHttpResponse` / `HostHttpBody` 拉取与关闭语义。

Runtime 增加相应分发、代理端口与目录安全投影。原有 `host.auth.list/get_runtime`、`host.keys.list`、`host.models.list`、`host.model.*`、`host.state.*` 和普通 `host.http.*` 的既有类型与实现未改；握手、调用预算、GPE2/HME1、挂起/恢复合同不变。打包 CLI 与管理页面桥源码无差异。

本插件的 GitHub 更新检查继续使用普通受管 `host.http.do_stream`，无需代理选择。模型检测仍由 `host.model.execute_stream` 显式绑定账号、Key、Provider 和协议，让宿主应用所选账号的代理、鉴权、配额与计量；不改为通用代理 HTTP，也不新增目录查询、凭据处理或直连路径。因此不因未使用的新接口提高兼容下限。

依据：[SDK 类型](https://github.com/zyycn/codex-proxy-rs/blob/c622f085748f812936a7371fcc85d1621fa72ca8/backend/crates/gateway-plugin/sdk/src/call/host.rs)、[HTTP 客户端](https://github.com/zyycn/codex-proxy-rs/blob/c622f085748f812936a7371fcc85d1621fa72ca8/backend/crates/gateway-plugin/sdk/src/client/http.rs)、[能力合同](https://github.com/zyycn/codex-proxy-rs/blob/c622f085748f812936a7371fcc85d1621fa72ca8/backend/crates/gateway-plugin/sdk/docs/capabilities.md)、[Runtime 代理端口](https://github.com/zyycn/codex-proxy-rs/blob/c622f085748f812936a7371fcc85d1621fa72ca8/backend/crates/gateway-plugin/runtime/src/callback/proxies.rs)。

## 宿主行为：重新授权可能改变真实身份

| 上游变化 | 本插件的适配结论 |
| --- | --- |
| v3.43.1 重新授权登录其他账号时更新真实身份、邮箱与套餐，保留本地名称和调度设置，并隔离旧会话 | 不能用本地 ID 或名称判断仍是同一账号。已有身份快照比较认证类型、上游用户 ID 与账号 ID，真实身份变化时拒绝继续、保留历史；正常令牌刷新仍可续测。既有协议测试分别覆盖这两条路径，无需新增转换层 |
| v3.44.0 将常规模型通用额度头归入 Codex，仅生图端点按活动计量项归类 | 本插件只做文本检测，继续使用宿主额度与每题返回用量，不自行解析限流头或写账号额度 |
| 账号连接测试区分发送前失败与上游响应，并补充代理配置、连接及隧道诊断 | 这是宿主连接测试与内部诊断变化，不是 SDK `PluginFault` 新字段。保留错误码、HTTP 状态、发送状态和已知请求 ID；模型失败仍暂停、不评分、不自动重发或直连 |

单题总预算 120 秒、流读取 90 秒、维护交接余量 150 秒、固定账号和两种检测参数均不变。Meow / ModelTrace 原始算法、基线与历史记录不变。

依据：[v3.43.1 发布说明](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.43.1)、[OAuth 重新授权](https://github.com/zyycn/codex-proxy-rs/blob/c622f085748f812936a7371fcc85d1621fa72ca8/backend/crates/providers/openai/src/credential/admin.rs)、[v3.44.0 发布说明](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.44.0)。

## UI：材质不再隐式改变圆角或尺寸

UI v0.9.1 删除柔光预设附带的控件 13px / 卡片 24px 圆角，并移除柔光侧栏的派生圆角。未自定义时，默认与柔光均使用控件 8px、卡片 18px、侧栏 0px；用户提供的字号、间距、尺寸和圆角继续优先。材质仍改变高光、渐变和阴影。

本插件不读取已移除的 `ThemePreset.customization`，仅使用稳定的组件导出、主题函数和 `--z-*` Token。生产页继续接受宿主的内联主题，不强制覆盖自定义圆角；旧宿主的弹层阴影回退保留。旧宿主提供旧尺寸时仍以其主题为准，不把新版默认值强加给旧宿主。

新增主题单测覆盖浅/深色、默认/自定义尺寸在材质切换时保持一致，以及默认圆角与卡片渐变；生产隔离页回归增加卡片和下拉弹层的实际计算圆角断言。

依据：[UI 源码差异](https://github.com/zyycn/codex-proxy-ui/compare/v0.9.0...v0.9.1)、[UI v0.9.1 发布说明](https://github.com/zyycn/codex-proxy-ui/releases/tag/v0.9.1)。

## 验证记录

环境：Windows、Rust 1.99.1、Node 24.19.0、pnpm 12.14.0、Python 3.13.7 / NumPy 2.5.1、真实 Chrome；使用现有 Node 24 运行时，不修改系统默认 Node。

| 检查 | 结果 |
| --- | --- |
| `cargo fmt --check --manifest-path backend/Cargo.toml` | 通过 |
| 指定 `MODEL_HEALTH_TEST_PYTHON` 后执行 `cargo test --locked --manifest-path backend/Cargo.toml` | 66 项通过；覆盖固定账号、身份变化与正常刷新、双方法、旧历史、后台错误/预算/恢复、RPC v7、SSE/WebSocket 与 Python/Rust 帧交叉验证；文档测试 0 项 |
| `pnpm --dir frontend install --frozen-lockfile`、`test`、`build` | 冻结安装、9 项测试、类型检查及生产构建通过 |
| `python -X utf8 -B -m unittest discover -s scripts/tests -v` | 5 项通过 |
| `scripts/browser-qa.mjs` | 双方法切换、选择保留、账号绑定、报告与历史、搜索、开始/暂停/继续/结束、浅/深/窄屏及空/错/加载状态通过 |
| `scripts/updates-browser-qa.mjs` | 更新检查与错误隔离、生产 IIFE 隔离页、复制、浅/深柔光主题和旧 Token 合同通过；实际卡片/控件/弹层圆角、渐变、阴影与内联主题一致；无直接 HTTP、控制台错误或横向溢出 |
| 发布配置 | workflow YAML、8 段 workflow Bash 及构建脚本语法、实际生成的 Release 说明、`git diff --check` 通过；SDK/CLI/锁文件固定提交及版本一致性由 Rust 合同测试核对 |

已查看当前生产隔离页柔光浅色、柔光深色和旧 Token 窄屏截图，位于本地忽略目录 `review/screenshots/sdk-theme-*.png`。旧 Token 检查模拟合同形状，未重新安装旧宿主；兼容依据另包括本次 SDK/页面桥标签差异及 [v3.37.2 适配记录](sdk-upgrade-2026-11-01.md)。

本机无 Docker；Linux 双架构内嵌引擎构建、CLI 打包及受限容器冒烟由推送后的 release workflow 执行，以对应 Actions 结果为准。未安装真实宿主或调用计费模型；真实检测仍由使用者主动触发。

## 更新与回退

更新同一 `local.model-health`，保留私有状态，不卸载重装。v0.4.3 与 v0.4.4 使用相同数据和协议，可在兼容宿主上切回旧插件制品；升级前保留旧包与宿主数据备份。宿主升级及数据库恢复遵循宿主发布说明，插件兼容不代替宿主恢复验证。制品仍仅支持 Linux glibc x86_64/ARM64。
