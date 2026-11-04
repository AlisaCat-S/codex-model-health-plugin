# v0.4.2 同步宿主 v3.39.1 SDK

2026-11-04 通过 GitHub Releases API 确认，最新正式宿主为 [v3.39.1](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.39.1)，UI 最新正式版仍为 [v0.8.0](https://github.com/zyycn/codex-proxy-ui/releases/tag/v0.8.0)。本次按标签提交对比 [v3.38.1 → v3.39.1](https://github.com/zyycn/codex-proxy-rs/compare/v3.38.1...v3.39.1)，覆盖 SDK、Runtime、打包 CLI、页面桥及相关模型执行策略，不使用浮动 `main`。

## 固定版本，保留本插件实际使用的合同

| 对象 | 升级前 | 本次目标 |
| --- | --- | --- |
| SDK / 打包 CLI | v3.38.1，`e0b7a841ca074f17e11dad73f39a159c75cb2fb1` | v3.39.1，`12c32fcdecb29da4e44a21bb33fbbf2aaf6a166d` |
| SDK crate / RPC | `0.1.0` / v7 | 不变 |
| UI Release 包 | v0.8.0 | 不变，保留冻结锁文件 |
| 插件版本 | v0.4.1 | v0.4.2；自动发布继续追加 UTC 时间戳 |
| 宿主清单范围 | `>=3.37.2, <4.0.0` | 不变 |

Cargo 依赖、锁文件、CI 安装 CLI 的提交和 README 构建命令使用同一固定提交；插件、后端与前端版本同步。仅更新 SDK 来源与插件补丁版本，不滚动更新其他依赖。

## SDK 差异：运行设置新增必填字段，但本插件不调用该接口

SDK 源码只有 `call/services/settings.rs` 变化：`RuntimeSettings`、`ReplaceRuntimeSettings` 增加 `max_retry_after_seconds: u32`，读取转写入的 `From` 实现同步复制此字段。这两个类型使用 `deny_unknown_fields`，新增字段也没有反序列化默认值，因此设置读写合同与旧宿主有差异，不能仅凭 RPC 版本不变认定所有接口兼容。

本插件使用 `host.auth.list/get_runtime`、`host.keys.list`、`host.models.list`、`host.model.*`、`host.state.*` 和 `host.http.*`，不调用设置服务、不构造这两个类型。以上回调类型、GPE2/HME1、握手与挂起/恢复授权合同均未变；management v2、maintenance v1、默认管理调用预算和已声明的维护预算不变。Runtime、`backend/apps/plugin-cli`、宿主管理页面桥与 `PluginPage.vue` 在两标签之间无源码差异，UI v0.8.0 与 `z` 主题桥继续使用。

因此保持兼容下限 v3.37.2、`runs` schemaVersion 1、16 槽位和现有历史，无数据迁移，也不添加设置适配层。旧宿主的既有验证见 [v3.37.2 适配记录](sdk-upgrade-2026-11-01.md)；本次重新验证 v3.39.1 SDK 的离线合同，没有重新安装两版真实宿主。

依据：[SDK 运行设置合同](https://github.com/zyycn/codex-proxy-rs/blob/12c32fcdecb29da4e44a21bb33fbbf2aaf6a166d/backend/crates/gateway-plugin/sdk/src/call/services/settings.rs)、[完整标签差异](https://github.com/zyycn/codex-proxy-rs/compare/v3.38.1...v3.39.1)。

## 宿主执行策略变化及处理

| 差异 | 对本插件的影响与处理 |
| --- | --- |
| v3.38.2 增加服务器建议 Retry-After 等待上限，默认 240 秒；超过上限不截短建议后提前重试，而是走已有安全换号或原错误出口 | 继续固定账号、Key、Provider 和协议，不主动换号或回退直连；宿主返回错误后暂停任务并保留发送状态。插件不改全局设置，后台单题总预算仍为 120 秒、模型流读取 90 秒、交接余量 150 秒；宿主允许等待更久不等于插件放宽预算 |
| 模型拒绝冷却仅依据精确 `model_not_found` 代码与允许的状态（无状态或 400/403/404）；`unsupported_value` 作为请求错误，不再按正文含有模型拒绝字样推断资格 | 资格判定继续归宿主管理；插件不解析错误文案来改模型、改号或自动重发。Key 可见列表仍不是所选账号的资格保证，错误不参与评分 |
| v3.39.1 恢复转发客户端 trace 头及对应 WebSocket metadata，`x-openai-fedramp` 保留多值；安装头使用所选账号的持久安装身份，地域和账号路由仍由部署配置控制 | 继续通过 `host.model.execute_stream` 走宿主原生链路，不复制头处理、合规或安装身份逻辑；后台调用不伪造浏览器入口头 |
| 同轮全量请求只回传归属已确认的 `x-codex-turn-state`，隔离 Key、账号、会话、线程与轮次 | 检测题仍为独立请求，`previous_response_id=None`、`store=false`，不新增轮次 token 持久化或跨题续接 |
| 插件敏感配置改为逐字段保留、替换与清除；宿主新增 Windows 发行物；配置竞争、代理删除锁及双栈探测延迟归属修复 | 本插件没有敏感配置 schema，不新增配置表单。插件制品继续只支持 Linux glibc x86_64/ARM64，宿主支持 Windows 不代表内嵌检测引擎可在 Windows 安装 |

依据：[Retry-After 实现与回归](https://github.com/zyycn/codex-proxy-rs/commit/0ff1a72919ae5732bc8ec96811c911d83a3124b8)、[模型拒绝分类修复](https://github.com/zyycn/codex-proxy-rs/commit/7b05b14a2bf29b56ddf4a9e889205c94b5c3db43)、[v3.39.1 发布说明](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.39.1)、[v3.39.0 发布说明](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.39.0)。

## 回归扩展：宿主错误保留发送状态，不在插件层重试

复用现有离线 RPC 宿主，将原来的账号资格拒绝测试扩展为三种 `host.model.execute_stream` 失败：`capacity / not_sent`、`upstream / HTTP 503 / sent`、`upstream / HTTP 503 / ambiguous`。每种都核对：

- 账号、Key、Provider、协议严格绑定；仅保存一次失败尝试，不伪造请求 ID，有效样本为 0
- 错误代码、HTTP 状态与发送状态原样保留，敏感诊断不进入历史；任务暂停并清除在途与排队状态
- 不读取或关闭不存在的模型流，不调用 `host.http.*` 直连回退，不自动重发
- 第二个排队任务正常完成，首任务仍只有一次失败尝试并保持暂停

这些夹具验证插件消费宿主错误的行为；Retry-After 的等待与资格冷却分类由上游 Core/Provider 回归覆盖，插件不重实现宿主调度器。检测算法、冻结基线、保守尝试预算和旧调用者的手动逐题入口保持原状。

## 本地验证

环境：Windows、Rust 1.99.1、Node 24.19.0、pnpm 12.14.0、Python 3.13.7 / NumPy 2.5.1。使用已安装的 Node 24 运行前端检查，不修改系统默认 Node。

| 检查 | 结果 |
| --- | --- |
| `cargo fmt --check --manifest-path backend/Cargo.toml` | 通过 |
| `MODEL_HEALTH_TEST_PYTHON=C:/Python313/python.exe cargo test --locked --manifest-path backend/Cargo.toml` | 66 项通过；覆盖扩展宿主错误用例、后台队列、双检测方法、账号/Key 绑定、旧历史、取消恢复和 SDK 帧交叉验证；文档测试 0 项 |
| `pnpm --dir frontend install --frozen-lockfile`、`pnpm --dir frontend test`、`pnpm --dir frontend build` | 冻结安装、8 项测试、类型检查和生产构建通过 |
| `python -X utf8 -B -m unittest discover -s scripts/tests -v` | 5 项通过，RPC v7 与模型事件夹具继续兼容 |
| 发布配置与版本 | workflow YAML 解析、双架构矩阵检查、Bash 语法和 `git diff --check` 通过；Rust 合同测试核对 SDK/CLI/锁文件同源、版本一致、兼容下限与新目标 |

本机无 Docker，Linux 双架构内嵌引擎构建、打包和受限容器冒烟由推送后的 release workflow 执行，以对应 Actions 运行结果为准。页面代码、UI 依赖与宿主页面桥未变，本次未重跑浏览器外观/交互。未部署真实宿主或调用计费模型；最终安装与真实请求验收由使用者主动触发。

## 更新与回退

在插件管理中更新同一 `local.model-health`，保留私有状态，无需卸载重装。v0.4.1 与 v0.4.2 使用相同数据、协议和主题桥，可在兼容宿主上切回旧制品；回退前保留宿主数据备份。低于 v3.37.2 的宿主仍需匹配更旧插件，互联节点须另外遵守 CPR Link 的兼容要求。
