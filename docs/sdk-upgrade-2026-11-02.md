# v0.4.1 同步宿主 v3.38.1 SDK

2026-11-02 通过 GitHub Releases API 查询，最新正式宿主为 [v3.38.1](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.38.1)，UI 最新正式版仍为 [v0.8.0](https://github.com/zyycn/codex-proxy-ui/releases/tag/v0.8.0)。本次逐项对比 [v3.37.2 → v3.38.1](https://github.com/zyycn/codex-proxy-rs/compare/v3.37.2...v3.38.1) 的 SDK、Runtime、打包 CLI、宿主页面桥和模型选号实现，不使用浮动 `main`。

## 固定版本，保留已有兼容范围

| 对象 | 升级前 | 本次目标 |
| --- | --- | --- |
| SDK / 打包 CLI | v3.37.2，`641f43b3030b1c68961e05d525e58ec6f4264a15` | v3.38.1，`e0b7a841ca074f17e11dad73f39a159c75cb2fb1` |
| SDK crate / RPC | `0.1.0` / v7 | 不变 |
| UI Release 包 | v0.8.0 | 不变，保留冻结锁文件 |
| 插件版本 | v0.4.0 | v0.4.1；自动发布继续追加 UTC 时间戳 |
| 宿主清单范围 | `>=3.37.2, <4.0.0` | 不变 |

SDK 公开类型、能力版本、回调线格式和宿主主题桥均未改变，因此不人为提高兼容下限。v3.37.2 的既有验证见[上次适配记录](sdk-upgrade-2026-11-01.md)，本次以 v3.38.1 SDK 重跑离线合同测试；这不等同于两版真实宿主安装测试。

Cargo 依赖、`Cargo.lock`、CI 安装 CLI 的提交以及 README 构建命令同步到同一固定提交。仅更新 SDK 来源与插件补丁版本，不滚动更新无关依赖。

## SDK 与宿主差异及处理

| 差异 | 对本插件的影响与处理 |
| --- | --- |
| SDK 私有模块 `client::read` 改名为 `client::pending_read`，内部引用同步；实现内容未变 | 插件只使用公开 `HostClient` / `PluginSession`，没有私有模块调用者；升级依赖即可，不复制上游实现或添加兼容包装 |
| SDK 清单测试修正有效前置样例；公开清单与合同源码未变 | 保持 manifestVersion 2、management v2、maintenance v1、RPC v7；继续使用原帧、GPE2/HME1 和挂起/恢复授权夹具 |
| Runtime 将私有状态 schema 配置与离线验证器移至 `package::state_schema`，其他流、代次模块整理目录 | `host.state.*`、CAS 与 schema 校验实现语义未变；保留 `runs` schemaVersion 1、16 槽位和全部历史，无数据迁移 |
| CLI、宿主兼容清单、`docs/plugins.md`、页面管理桥和宿主前端依赖未变 | CLI 仍随 SDK 同源锁定；UI v0.8.0 与 `z` 主题桥继续使用，不改页面布局或重写桥接 |
| v3.38.1 统一原生 Responses 的有效目录成员资格与账号模型黑白名单，固定账号、亲和和权重不能绕过；API Key 目录按账号与凭据版本隔离 | 继续明确绑定账号 ID、Key ID、OpenAI Provider 与协议；Key 可见模型不代表每个账号都有资格。宿主拒绝时保留公开错误、暂停本任务、继续其他排队任务，不换号、不直连、不自动重发 |
| v3.38.0 增加账号/模型组合的明确拒绝冷却，出站移除 `sentry-trace` / `baggage` | 冷却与出站策略由宿主执行，插件不复制调度规则或补回遥测头；仍由用户确认后手动继续 |
| CPR Link v2 不兼容 v1 快照，互联能力改为可选块及命名预算窗口 | 插件不读取互联快照或预算窗口，不需要新增协议解析；若所选账号为 CPR 互联上游，宿主两端需按上游要求协调升级并手动刷新互联账号 |

目录缺失、过期或套餐未知时，宿主仍按其策略交由上游验证；插件不把列表查询当成账号资格预检，也不为此增加额外模型请求。检测算法、冻结基线、保守尝试预算和旧调用者的手动逐题入口保持不变。

依据：[SDK 差异](https://github.com/zyycn/codex-proxy-rs/compare/v3.37.2...v3.38.1)、[模型资格修复](https://github.com/zyycn/codex-proxy-rs/commit/96a292dd0f6cc2a22e6264d7b9b7ce286f9e8b5e)、[v3.38.1 Runtime 模型回调](https://github.com/zyycn/codex-proxy-rs/blob/e0b7a841ca074f17e11dad73f39a159c75cb2fb1/backend/crates/gateway-plugin/runtime/src/callback/model.rs)、[宿主 Release 升级事项](https://github.com/zyycn/codex-proxy-rs/releases/tag/v3.38.1)。

## 新增回归：模型资格拒绝不能导致换号或自动重发

离线 RPC 宿主在 `host.model.execute_stream` 返回 `capacity / not_sent`，不创建模型流。测试核对：

- 账号、Key、Provider、协议仍严格绑定；仅保存一次失败尝试，不伪造请求 ID，不计入有效样本
- 任务暂停并清除排队与在途状态；错误详情中的敏感诊断不落入历史，不对不存在的流读取或关闭
- 第二个排队任务正常完成，首任务仍只有一次尝试；不触发 `host.http.*` 直连回退

这是对插件收到宿主拒绝后的行为验证；账号目录筛选本身由上游 Provider 的合同测试覆盖。

## 验证记录

本地环境：Windows、Rust 1.99.1、Node 24.19.0、pnpm 12.14.0、Python 3.13.7 / NumPy 2.5.1。

| 检查 | 结果 |
| --- | --- |
| `MODEL_HEALTH_TEST_PYTHON=C:/Python313/python.exe cargo test --locked --manifest-path backend/Cargo.toml` | 66 项通过：含新增资格拒绝回归、后台队列、双检测方法、账号/Key 绑定、错误脱敏、旧历史、取消恢复和 SDK 帧交叉验证；文档测试 0 项 |
| `pnpm --dir frontend install --frozen-lockfile`、`pnpm --dir frontend test`、`pnpm --dir frontend build` | 冻结安装、8 项测试、类型检查与生产构建通过 |
| `python -X utf8 -B -m unittest discover -s scripts/tests -v` | 5 项通过，RPC v7 与模型事件夹具继续兼容 |
| 发布配置与版本 | workflow YAML 解析、Bash 语法和 `git diff --check` 通过；Rust 合同测试核对 SDK / CLI / 锁文件同源、版本一致及兼容下限/目标范围 |

本机没有 Docker，Linux x86_64/ARM64 内嵌引擎构建、打包和受限容器冒烟由推送后的 release workflow 执行。页面代码、UI 依赖与宿主主题桥均未变，本次未重跑浏览器外观/交互；上次结果见原适配记录。未安装真实宿主或调用计费模型，最终安装与真实请求验收由用户主动触发。

## 更新与回退

在插件管理中更新同一 `local.model-health`，保留私有状态；无需卸载重装。v0.4.0 与 v0.4.1 的数据、协议和主题桥一致，可在兼容宿主上切回旧制品。低于 v3.37.2 的宿主仍需匹配更旧插件；互联节点的宿主回退还须遵守 CPR Link v2 的独立兼容要求。
