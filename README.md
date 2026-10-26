# 账号模型体检 · Codex Proxy 插件

为 [Codex Proxy RS](https://github.com/zyycn/codex-proxy-rs) 提供独立的账号模型体检页面：选择已有账号与计量 Key，通过原生代理和请求链路运行 **Meow / ModelTrace** 两种行为指纹检测，无需再次填写 API 地址或密钥，也不修改主项目。

[下载本分支最新构建](https://github.com/AlisaCat-S/codex-model-health-plugin/releases/latest) · [反馈问题](https://github.com/R-lmmortal/codex-model-health-plugin/issues) · [插件使用规范](https://github.com/zyycn/codex-proxy-rs/blob/main/docs/plugins.md)

![插件页面（模拟数据，不代表真实检测结果）](docs/screenshots/overview.png)

## 来源与致谢

本插件集成以下项目的检测算法与基线，感谢原作者；不是自行发明的“降智评分器”，也不是上游官方插件。

| 项目 | 集成内容与固定版本 | 许可证 |
| --- | --- | --- |
| [Meow LLM Detector — chen-006](https://github.com/chen-006/meow-llm-detector) | 题目、响应解析、答案归一化与行为概率评分；引擎 4.5.4 / 基线 4.5.3-predictive.2；[提交 dc608d5](https://github.com/chen-006/meow-llm-detector/tree/dc608d5c097abf96575d5b34f49952ddbd27c281) | [PolyForm Noncommercial 1.0.0](vendor/meow/LICENSE) |
| [ModelTrace — xqy2006](https://github.com/xqy2006/ModelTrace) | 原始指纹算法与统一候选库；[提交 6cd4a8f](https://github.com/xqy2006/ModelTrace/tree/6cd4a8ff0f3f4e49d6d6969dd2fbadfa1569fde2) | [MIT](vendor/modeltrace/LICENSE) |

宿主集成使用 [Codex Proxy 公开 SDK](https://github.com/zyycn/codex-proxy-rs/tree/8c8618aa0f841638262262e3338c115bc075f125/backend/crates/gateway-plugin/sdk)（v3.33.0，插件 RPC 协议 v7）、[@codex-proxy/ui](https://github.com/zyycn/codex-proxy-ui) v0.7.0，并参考 [官方插件示例与规范](https://github.com/zyycn/codex-proxy-plugins)。

本次升级到 **RPC v7** 的预算、协作调度、回调回收和 UI 差异见 [SDK 适配分析](docs/sdk-upgrade-2026-10-26.md)。插件 **v0.3.0 对应宿主 v3.33.0**，当前构建要求宿主 **3.33.0+**。宿主 v3.33.0 仅支持 RPC v7；3.32.x 及更早宿主应保留匹配的旧插件，旧 RPC v5/v6 插件须更新 SDK、重新构建和打包，不能只改清单。已发布制品以包内清单为准。

完整集成包按 [PolyForm Noncommercial 1.0.0](LICENSE) 分发，包含非商业用途条件；ModelTrace 等第三方文件仍保留各自的许可证。本仓库是源码公开项目，不将整个包宣称为 MIT 或无商业用途限制。原始版权声明、第三方组件声明与依赖许可证见 [NOTICE](NOTICE)，安装包中也附带相关文件。

## 安装与兼容性

| 项目 | 当前支持 |
| --- | --- |
| 插件 ID / 版本 | `local.model-health` / `0.3.0` |
| 宿主清单范围 | `>=3.33.0, <4.0.0`（插件 RPC 协议 v7、management v2）；源码适配与离线协议验证基于 3.33.0 SDK |
| Release 平台 | Linux x86_64 与 ARM64（aarch64），glibc 2.36+（如 Debian 12）；不适用于 Alpine/musl 或 Windows |
| 运行方式 | `trustedProcess`，插件以宿主系统身份运行，安装代表完整信任；不是操作系统沙箱 |
| 扩展能力 | 独立管理页面；不注册请求中间件、调度器、观察器或自动维护任务 |

在 **插件管理 → 安装插件 → GitHub** 中填写：

```text
仓库：AlisaCat-S/codex-model-health-plugin
版本标签：留空查询本分支最新构建（v0.3.0-<UTC 时间戳>）
```

按服务器架构选择制品：AMD64/Intel 64 选 `local.model-health-<版本>-x86_64-unknown-linux-gnu.tar.gz`，ARM64 选 `local.model-health-<版本>-aarch64-unknown-linux-gnu.tar.gz`，核对平台与摘要后安装并启用。也可从 [Releases](https://github.com/AlisaCat-S/codex-model-health-plugin/releases) 下载对应文件，通过“上传包”安装。请不要上传 GitHub 自动生成的 **Source code (zip/tar.gz)**，它们是源码而不是插件制品。

版本号由 GitHub Actions 自动发布生成，格式为「语义版本 + UTC 时间戳」，如 `v0.3.0-20261026.1200`；分钟数不带前导零（05:04 记为 `20261024.504`）以符合 semver 预发布标识符规则，数值比较仍严格单调。详见 [docs/release-automation.md](docs/release-automation.md)。

Release 同时提供同名 `.tar.gz.sha256`；下载两个附件后可校验（以 x86_64 为例，aarch64 同理）：

```sh
sha256sum -c local.model-health-<版本>-x86_64-unknown-linux-gnu.tar.gz.sha256
# macOS：shasum -a 256 -c local.model-health-<版本>-x86_64-unknown-linux-gnu.tar.gz.sha256
```

保留 `local.model-health` 是为了让原先本地安装的版本继续沿用同一插件身份与历史。原项目为 [R-lmmortal/codex-model-health-plugin](https://github.com/R-lmmortal/codex-model-health-plugin)；本分支构建发布到 [AlisaCat-S/codex-model-health-plugin](https://github.com/AlisaCat-S/codex-model-health-plugin)。已有本地安装可在插件详情设置 GitHub 更新来源，或上传新版后确认切换；不要为了更新而删除原配置或私有数据。

## 使用

1. 按上述方式安装并启用插件。
2. 打开「账号模型体检」，选择已启用的 OpenAI 账号和已有 Key 的名称。账号优先显示去除首尾空白后的邮箱；没有邮箱时显示账号名称。新建检测保存该显示名称，旧历史仍保留检测当时的名称；请求绑定始终使用账号 ID。
3. 选择该 Key 可见的请求模型及检测方法。Meow 选择对照模型和 36 / 72 / 108 题档位；ModelTrace 使用统一候选库，固定 3 轮数字选择。切换方法保留账号、Key 和请求模型。
4. 点击「开始检测」，任务进入服务器后台队列。多个任务按开始或继续的顺序串行执行，宿主按所选 Key 计量；刷新、隐藏、关闭或离开页面不会暂停测试。
5. 失败会暂停对应任务，其他排队任务继续。点「继续检测」才重新排队；每档最多追加 50% 重试预算。手动暂停或结束时，已发出的当前题仍会保存结果和用量。
6. 随时返回「任务列表」，点进任务查看进度、报告及请求明细；页面可见时每 2 秒更新状态。仅在 16 个槽位满后替换最早的已结束记录，不覆盖未结束任务。
7. **服务器或插件重启后，所有未完成任务暂停，需手动继续。** 中断题按一次未知结果计入尝试预算，已成功样本不重复发送。

Meow 报告给出行为匹配、行为偏移或证据不足。ModelTrace 报告展示前 5 个候选模型及家族概率，完整 18 个候选的结果保存在任务报告中；满 3 个有效样本才给出「更接近」结论。概率是在冻结候选库内、均匀先验下的相对分布，库外模型也会归到已有候选，不代表真实身份概率。

两种方法都不是智商分数或模型身份认证，分数不混用。仍只选择宿主 OpenAI 账号；ModelTrace 候选库包含 GPT / Claude 家族，不等于新增 Claude 原生账号接入。只有相同方法、基线、模型与采样条件的复测才适合比较。

## 数据与执行

### 上游更新检查

右侧「项目来源」显示 [Meow](https://github.com/chen-006/meow-llm-detector) 和 [ModelTrace](https://github.com/xqy2006/ModelTrace) 的 GitHub 地址、内置提交与各自的「检查更新」按钮。内置来源来自 `vendor/meow-source.json` 和 `vendor/modeltrace/SOURCE.json`。宿主的隔离页面不开放新窗口，地址可点选或用旁边按钮复制，在浏览器打开；提交有差异时同样提供可复制的比较地址。

只有点击按钮才通过公开 SDK 的 `host.http.*` 读取对应仓库默认分支提交，并按 GitHub compare 的 ahead / behind / diverged / identical 区分结果。请求不使用账号、Key 或模型接口；打开页面不访问 GitHub，检查失败不影响开始、续测或检测历史。每个仓库的成功结果在插件进程内复用 5 分钟，展示实际检查时间；失败不缓存、不自动重试。每次检查限时 15 秒，单个响应最多 256 KiB。网络、限流或格式异常明确显示未确认，不当作最新版本。

检查比较的是上游仓库提交，不是可安装插件版本；文档等变化也会提示新提交。检测引擎、算法与基线随插件编译打包，保留「手动升级」：先适配并验证上游变更，再重新构建安装包，从插件管理更新同一插件。检查按钮不会下载或执行上游代码，不改正在运行任务的冻结基线与历史评分。

### 模型检测

- 使用 `host.auth.list/get_runtime` 的非秘密账号资料、`host.keys.list` 和 `host.models.list`；页面只提交账号 ID 与 Key ID，不读取原始凭据。
- 每个 `host.model.execute_stream` 都显式指定 `account_id`、`client_key_id`、`provider=openai` 和 `protocol=openai`。主服务负责代理、鉴权、配额与最终计量；插件不搭建另一套 HTTP 出口。
- 后台通过宿主 `maintenance`／`plugin.reconcile` 推进，使用维护调用自身的宿主客户端。代理、上游请求头及客户端参数按宿主有效配置应用；没有浏览器入口的后台调用不伪造入口 IP 或 User-Agent。宿主拒绝或代理失败时暂停，不回退为插件直连上游。
- 维护调用声明 1 小时有限预算，单题总执行限时 120 秒，模型流读取仍限时 90 秒。剩余不足 150 秒时不派发下一题，交回宿主后继续队列，轮次交接最多等待约 30 秒。持久化失败时停止继续派发并暂停未完成任务，等待手动继续。
- 网页在开始及继续时显式传入 `background:true`。兼容旧调用者：`runs/start` 省略该字段仍创建手动逐题任务，原 `runs/step` 可用；后台托管任务拒绝逐题调用。旧记录在新页面点击继续后转入后台队列。任务新增可选的 `background`、`queued_at`、`task_error`，沿用原状态枚举与存储 schemaVersion 1。
- 支持宿主返回的 Responses SSE 与 WebSocket 事件，统一交给原解析器判定完成、错误与拒答；读至宿主 EOF 后才评分。非流式错误只显示载荷类型及可用的 HTTP 状态/传输方式，不保存原始错误正文；用请求 ID 关联宿主详情。
- 完整保留 Meow 的题目、参数、SSE 解析、答案归一化和概率评分。原源码放在 `vendor/meow`，文件哈希没有改变。Meow 版本 4.5.4；基线内容哈希冻结在每次任务中。
- ModelTrace 的原始 `fingerprint.py` 和统一候选库固定在上游提交 `6cd4a8ff0f3f4e49d6d6969dd2fbadfa1569fde2`，来源及逐文件哈希见 `vendor/modeltrace/SOURCE.json`。复用原始随机题目生成、数字解析、Hellinger / 有序数字块融合、温度校准和家族聚合，不引入原项目的网络服务或 API Key 表单。
- ModelTrace 生成 3 份独立题目后持久化，断点续测与失败重试保留题目和检测方法。通过现有 Responses 流发送单条用户消息，采样使用供应商默认值，不套用 Meow 的 256-token 短答参数。沿用插件模型流读取阶段 90 秒上限（不含此前的请求建立）、后台串行执行、遇错人工续测和 50% 重试预算（3 个有效样本、最多 5 次尝试），而非原网页的自动重试流程。
- 后台任务以带排队时间的 `ready` 表示排队，逐题 `ready → running → ready/paused/completed`；显式停止转 `stopped`。发送前先写 pending，异常中断后按一次未知结果计入预算。首轮所有题优先于重试；成功样本不重复计数。
- 全局推理并发为 1；网络等待时释放状态锁。页面暂停/结束保留当前题的结果。每题发送前及续测时核对账号 ID、平台、启用状态和冻结的上游身份；Cookie 回写、令牌刷新导致的凭据版本变化不视作换号，认证类型或上游身份变化则中止续测。
- 缺少稳定上游身份的账号，在已有样本且凭据更新时要求新建检测。旧检测没有身份快照时，只有尚无样本或凭据版本未变才会补存当前身份；其他旧检测保留历史，结束后新建一次即可使用稳定身份校验。
- 状态只写插件私有 `runs` 命名空间，16 槽位，CAS 更新；不改主服务数据库结构、不安装观察器/中间件/维护钩子。
- 样本保留请求 ID、用量、错误与最多 256 字节回答摘录。Meow 保存归一化类别；ModelTrace 保存完整有序数字（最多 4096 个，超出则明确报错），用原评分器的有效长度判定剔除短答。评分不使用展示摘录，展示截短会标明。
- 历史报告保留检测方法、基线版本和内容哈希，不因表单切换或后续基线更新重新计算。缺少方法字段的旧记录按 Meow 读取和续测，不改变原来的账号身份校验。
- 主服务的模型映射、提示词或中间件可能影响实际响应，因此报告描述的是当前配置链路的行为，不把它解释成纯模型能力证明。
- Linux 安装包内含 Rust 插件及 Python/NumPy 检测引擎，不要求服务器另装 Python。引擎在宿主分配的插件实例目录内创建权限 0700 的工作目录，并将子进程的 `TMPDIR` 指向这里；支持非 root、空环境、只读根目录及 `/tmp:noexec`。宿主回收实例目录时会清理残留文件；不是 Alpine/musl 包。

## 构建与验证

构建工具：Docker Buildx、Node 24+、pnpm 12.14、Python 3.9+（安装包冒烟测试）、Rust 1.99.1（构建打包 CLI）。SDK 与 CLI 固定为同一个宿主提交 `8c8618aa0f841638262262e3338c115bc075f125`（v3.33.0，插件 RPC 协议 v7）。UI 使用官方固定版本 Release 归档，不再从 Git 源码安装或执行其构建脚本。前端依赖锁定在 `frontend/pnpm-lock.yaml`；不要直接换成浮动 `main`。在仓库根目录执行：

```sh
cargo install --git https://github.com/zyycn/codex-proxy-rs.git \
  --rev 8c8618aa0f841638262262e3338c115bc075f125 \
  --locked --root .tools/cpr-cli codex-proxy-plugin-cli
CPR_PLUGIN_BIN="$PWD/.tools/cpr-cli/bin/cpr-plugin" ./scripts/build-linux.sh
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend test
pnpm --dir frontend build
```

`./scripts/build-linux.sh [目标]`（默认 `x86_64-unknown-linux-gnu`，可选 `aarch64-unknown-linux-gnu`）在 Docker 中构建内嵌 Python/NumPy 引擎、运行 Rust 的 `bundled-engine` 单测、编译对应架构的 Linux 二进制、构建页面，最后使用官方 CLI 生成 `dist/*.tar.gz` 与校验文件。打包后在非 root、空环境、只读根目录和 `/tmp:noexec` 容器中运行离线协议验收；默认使用 `debian:bookworm-slim`，可通过 `SMOKE_IMAGE` 指定已准备好的 Debian 12 兼容镜像，`SMOKE_PLATFORM` 默认与目标架构一致。

### 自动构建发布

`.github/workflows/release.yml`：推送 `main` 自动构建并发布 Release；也可在 Actions 页面手动触发（`workflow_dispatch`），勾选 `dry_run` 可只构建验收不发布，便于在分支试跑。每次运行用原生 runner（`ubuntu-latest` / `ubuntu-24.04-arm`）同时构建 x86_64 与 aarch64 两种制品，版本号自动生成为「语义版本 + UTC 时间戳」（如 `v0.3.0-20261026.1200`），并附同名 `.sha256`。设计与取舍见 [docs/release-automation.md](docs/release-automation.md)。

直接运行不带 `bundled-engine` 的本机 `cargo test` 默认使用开发用 `meow-llm-detector:4.5.4` Docker 镜像。若本机已有 Python 和 NumPy，可显式指定 `MODEL_HEALTH_TEST_PYTHON` 为 Python 可执行文件路径，不会根据 Docker 是否安装自动切换环境。例如 PowerShell：

```powershell
$env:MODEL_HEALTH_TEST_PYTHON='C:/Python313/python.exe'
cargo test --locked --manifest-path backend/Cargo.toml
python -X utf8 -B -m unittest discover -s scripts/tests -v
```

发布构建仍使用内嵌引擎。构建脚本同时校验 Python 冒烟编码与 Rust SDK 的 RPC v7、GPE2/HME1 格式；安装包冒烟覆盖挂起/恢复授权/回调消费、SSE、两种 WebSocket 封套、多批次和独立 EOF。修复设计与验收范围见 [Responses 流修复方案](docs/investigation/2026-10-24-arm-detection-failures.md)。

浏览器预览显式标注「模拟」，生产构建会剔除模拟宿主与模拟数据模块。`scripts/browser-qa.mjs` 支持 `PLAYWRIGHT_PATH`、`CHROME_BINARY`、`PREVIEW_URL`，检查双方法切换、选择保留、报告隔离、开始→暂停→继续→结束→历史，以及浅/深/窄屏、空/错/加载状态。`scripts/background-browser-qa.mjs` 使用独立于页面的模拟宿主，验证刷新、关闭、离开后重新进入任务、轮询断连恢复及旧详情响应不会覆盖新选择。`scripts/updates-browser-qa.mjs` 使用相同环境变量，验证来源地址、更新检查状态和检查失败时模型表单仍可使用，并在 `sandbox="allow-scripts"` 的隔离页面验证生产资源与地址复制。

`python3 scripts/package-smoke.py /absolute/path/plugin.tar.gz --continuous --modeltrace --updates` 在离线 SDK 宿主夹具中检查安装包、两种检测、更新回调和互不干扰。另加 `--updates-live` 时仅由测试宿主访问两个公开 GitHub API（不调用真实模型），验证安装包实际解析和缓存上游提交；网络失败会让该项验收失败。

离线协议验收使用固定模拟回调，不向真实模型发送请求。安装后的最终验收是用一个账号分别执行 Meow 快速档和 ModelTrace 三轮检测，核对主项目使用记录中的账号与请求 ID。安装与真实计费检测由使用者主动触发。

## 回退

宿主 v3.33.0 仅接受 RPC v7，不能在该宿主上回退到 RPC v5/v6 插件；如需回退旧协议，须同时回退到匹配的旧宿主。

安装新版时在插件管理中更新同一插件，保留现有 `runs` 状态。升级前保留旧安装包并备份宿主数据；需要回退时使用插件详情中的“回退版本”或“切换版本”，选择已安装、已接受且兼容的旧制品。配置回退不等于恢复私有数据，不能用卸载重装代替历史备份。停用本插件会停止插件功能，不修改主项目代码或其他插件。

## 后续开发提示词

```text
继续开发 codex-model-health-plugin。先读 README.md、plugin.json、engine/worker.py、backend/src 和现有协议测试。
沿用 @codex-proxy/ui 与当前管理桥；保持 Meow / ModelTrace 原源码不变、方法与基线冻结、旧 Meow 记录兼容、账号/Key 显式绑定、预算保守计数、错误不参与评分。
只改所请求的功能；补充离线协议测试和真实浏览器交互检查；不要自动部署或执行付费检测。
```
