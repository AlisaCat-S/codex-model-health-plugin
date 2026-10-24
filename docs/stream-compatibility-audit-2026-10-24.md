# 模型检测连续失败：SDK v5 流兼容排查（修复前记录）

本文记录 `6d07dff` 基线的排查与复现。后续两个提交的 review、最终实现及当前验收范围见 [Responses 流修复方案](investigation/2026-10-24-arm-detection-failures.md)。

## 结论与优先处理

**已确认一个足以造成此次现象的 SDK 迁移缺陷：插件拒绝新版宿主正常返回的 `WirePayload::WebSocket`。优先补齐 Responses WebSocket 事件适配，而不是回退题库、增加重试或重新编译 ARM。**

原始提交 `6d07dff` 的 Rust 后端 + 当前 Python 引擎，在 Windows x86_64 离线宿主夹具中复现了与现场一致的前六个样本顺序、2 个有效样本、4 个失败样本和原错误文案。输入为正常回答，不需要上游限流、凭据失效或 ARM 故障。

现场这四个请求究竟收到 WebSocket 还是非流式错误正文，仍需宿主请求详情裁决。已向使用者索取实际宿主版本与首个失败请求的 transport、状态码和错误原因。代码缺陷及其复现已成立；现场归因优先级为 WebSocket 兼容缺口，其次才是被统一文案掩盖的真实上游错误。

本次为原因排查，没有部署、发布或调用真实计费模型。

## 1. 迁移遗漏发生在返回值语义，不是 RPC 分帧

版本链：

- 插件 `2036ed3` 将 SDK 从 `fef52b3717019513108733549508377a309f129d` 升至 `76291f448cdf1d1da2027da32b7c949deb998c7a`（宿主 v3.30.2、RPC v5）。
- 宿主中间提交 [`b8479b59`](https://github.com/zyycn/codex-proxy-rs/commit/b8479b59dbafbe84ffbbd2d0ff3ccea6cfa59164) 新增 `WirePayload::WebSocket`，并改变向插件投影原始消息的顺序。
- 插件 `backend/src/host.rs` 没有随 SDK 升级修改。旧的兜底 `_` 分支使新增枚举变体仍能编译，却在运行时拒绝正常消息。

旧宿主 `runtime/src/callback/facts.rs::project_wire`：

```text
原始 HTTP 正文 → RawBody
完整 JSON 正文 → RawJson
has_json_data → Json
原始 SSE → RawSse
```

新宿主在 `has_json_data` **之前**增加：

```text
raw_websocket_message → WebSocket { event, data, message }
```

正常 WebSocket Responses 事件本来就既带解析后的 JSON，又带原始 WS 文本。因此旧宿主将其投影为插件接受的 `Json`，新宿主将其投影为插件拒绝的 `WebSocket`。不能因为插件的 `host.rs` 没变就排除 SDK 迁移。

可复核源文件（均固定在 `76291f4`）：

- [SDK 枚举定义](https://github.com/zyycn/codex-proxy-rs/blob/76291f448cdf1d1da2027da32b7c949deb998c7a/backend/crates/gateway-plugin/sdk/src/call/model/mod.rs#L149-L179)
- [宿主 wire 投影](https://github.com/zyycn/codex-proxy-rs/blob/76291f448cdf1d1da2027da32b7c949deb998c7a/backend/crates/gateway-plugin/runtime/src/callback/facts.rs#L263-L300)
- [OpenAI 原始 WS 与 JSON 视图同时保留](https://github.com/zyycn/codex-proxy-rs/blob/76291f448cdf1d1da2027da32b7c949deb998c7a/backend/crates/providers/openai/src/transport/canonical.rs#L497-L514)

`host.model.execute_stream` 的含义是返回可读取的模型执行事件流，不保证上游传输一定是 HTTP SSE。请求正文中的 `stream: true` 也不等于强制 HTTP。

## 2. 原文案准确说明了什么

`backend/src/host.rs:297-307` 原代码接受 `Json`、`RawSse`；拒绝 `WebSocket`、`RawJson`、`RawBody`。

出现这条文案意味着：SDK 已成功解码事件批次，事件有 wire、协议为 `openai`，然后命中了不支持的载荷变体。**它不证明上游请求失败，也不代表空流。**

实际分支：

| 输入 | 原插件结果 |
| --- | --- |
| 正常 Responses `Json` | 接受，交 Python 解析 |
| 正常 Responses `RawSse` | 接受，交 Python 解析 |
| 正常 Responses `WebSocket` | 错误地报“模型未返回 Responses SSE”并关闭执行流 |
| `RawJson` / `RawBody` | 同一句错误，正文原因丢失 |
| 空流：`events=0, end=true` | Rust 返回空字符串，Python 报 `truncated_stream` |
| `Json` 内的原生 `type:error` | Python 报 `upstream_stream_error` |
| SDK 批次无法解码 | “模型事件批次格式错误”，不是本次文案 |

这也区分了“接口返回错误”和“插件主动拒绝正常回答”。`execute` 随后调用 `host.model.stream_close`；宿主会取消未完成执行，因此宿主记录出现取消可能是插件拒绝消息的后果。

## 3. 为什么可能先成功一两题，再持续失败

宿主默认优先 WebSocket；普通新请求允许在 WebSocket 快路径等待超过 **800 ms** 后改用 HTTP SSE。池化 opening 可以在后台继续，建立好的连接可供后续同池请求使用。

源文件：

- `providers/openai/src/provider/observation.rs:657-662`：未强制 HTTP 时选择 `PreferWebSocket`。
- `providers/openai/src/transport/client_sse.rs:369-416`：新链的 WS 快路径超时后回退 HTTP。
- `providers/openai/src/transport/websocket/coordinator.rs:35, 317-331, 352-394`：800 ms 预算、后台 opening 继续、连接回池。

因此 HTTP 成功、后续 WS 失败是一条真实存在的执行路径；连接状态和网络建连时间足以改变插件收到的变体。换 CPU 架构不是触发该缺陷的必要条件。

**不能直接断言这六道不同题复用了同一条连接。** 默认本地会话锚点还会根据模型、指令、首条用户文本派生，池键包含会话。题目不同可产生不同池键。现场应核对 `transport` 和 `transport decision`：例如 `http2_ws_budget_exhausted`、`ws_connected_fast`、`ws_reused`。源码证明传输会分流，实际在哪一次切换由日志确认。

## 4. 离线复现与检查结果

### 固定输入

- 被测生产源码：Git 提交 `6d07dff` 的隔离快照。
- 依赖：原 `backend/Cargo.lock`，SDK 固定 `76291f4`。
- 运行环境：Windows x86_64，Rust 1.99.1，Python 3.13.7，NumPy 2.5.1。
- 使用真实 `PluginSession`、RPC v5 编解码、真实管理接口/状态机、真实 Python worker。
- 宿主回调（账号/Key 元数据、状态存储、模型执行等）由离线夹具提供；不访问真实账号和模型。
- 夹具复用 `backend/tests/protocol.rs`，将 Docker 引擎启动改为本地 Python，并增加 wire 类型注入；流以事件批次 `end=false` 后接独立空 EOF，符合真实宿主读取过程。

### 复现 A：同样的正常回答，换封套即失败

8 种返回形态的断言全部通过：`Json`、`RawSse` 成功；`WebSocket` 的 `data=Some` 和 `data=None` 两种形态都触发原文案；非流式错误正文同样触发原文案；空流与原生 JSON 错误分别得到 `truncated_stream` 和 `upstream_stream_error`。

### 复现 B：与现场一致的连续样本序列

| 次数 | 样本 | 注入封套 | 样本状态 | 有效样本累计 |
| --- | --- | --- | --- | --- |
| 1 | `gpt__ZH006:0` | Json | ok | 1 |
| 2 | `gpt__ZH027:0` | Json | ok | 2 |
| 3 | `gpt__ZH071:0` | WebSocket | error | 2 |
| 4 | `gpt__b80_letter_count:0` | WebSocket | error | 2 |
| 5 | `gpt__rand_bird:0` | WebSocket | error | 2 |
| 6 | `gpt__rand_country:0` | WebSocket | error | 2 |
| 7 | `gpt__ZH006:1` | Json | ok | 3 |

第 3–6 次均保存原始 SSE 错误文案，每次失败后执行显式 resume，恰好产生 4 次 stream_close。第 7 次换回 `Json` 后立即成功，说明这条复现路径中没有引擎永久失效或执行锁泄漏。

### 相关既有检查

- 后端库单测：10 项通过。
- 隔离夹具：完整 36 题及重开历史、ModelTrace 同宿主路径及冻结计划续测、网络错误暂停，各 1 项通过。
- Python：请求参数沿用原题、拒绝截断/拒答、失败不计成错误答案、ModelTrace 错误不归因，4 项通过。

本地复现文件保存在 `.build/stream-audit/`（忽略目录），未改动生产源码。当前机器可重放：

```powershell
$env:PYTHONUTF8='1'
$env:CARGO_TARGET_DIR=(Join-Path (Get-Location) 'backend/target')
cargo test --offline --locked --manifest-path .build/stream-audit/Cargo.toml audit_ -- --nocapture
```

ARM 发布包及真实宿主端到端未执行；离线结果证明与 CPU 无关的兼容缺陷，不替代 ARM 制品验收。

## 5. 其他变更、失败路径和排除依据

### 上游同步不改变此次 Meow 请求路径

`407aad9` 没有修改 `engine/worker.py`、`engine/modeltrace_adapter.py`、`vendor/meow/gpt56_vnext/protocol.py` 或当前加载的 `gpt56_vnext/baselines/v4.5.3`。

Meow 新增的 GPT 6.1 数据在 `benchmarks/official/`；引擎仍通过 `BUNDLED_BASELINES="v4.5.3"` 加载旧内置基线。这些新参考文件没有改变本次六道题的请求和解析。六题均使用 `reasoning.effort=low`、`max_output_tokens=128`、`stream=true`、`store=false`，成功与失败之间不存在这些参数的差异。

ModelTrace 同步改变候选库（17→18），不改变共同的 Rust 模型流入口。旧 ModelTrace 计划因库指纹变化可能报 `baseline_changed`；这是另一条有明确文案的路径，不能解释本次 Meow SSE 错误。

### ARM 构建未发现能解释此文案的特有分支

`scripts/build-linux.sh` 对 Rust 与 PyInstaller 都使用目标对应的 Docker `--platform`；CI 两架构分别在原生 runner 构建。模型事件使用 SDK 定长大端编码，不依赖 CPU 原生字节序。检测和网络路径也没有 ARM 专用逻辑。

旧 x86 插件（协议 v2）不能作为新 v5 宿主的有效对照。正确的架构对照必须让两种制品使用相同源码、SDK、宿主版本、账号配置及传输条件。已在 x86_64 复现同一缺陷，因此不应优先把时间花在 QEMU 或重编译上。

### CI 为什么通过

`backend/tests/protocol.rs:359-378` 和 `scripts/package-smoke.py:208-215` 都只生成 `WirePayload::Json` 的成功完成事件，没有覆盖新增的 WebSocket 变体。二者还将完成事件和 `end=true` 放在同一批次；真实宿主通常先返回事件，最后另发空 EOF。

SDK 升级只修通分帧、头字段、管理能力版本和编译，不足以验证模型事件语义兼容。`_` 匹配又阻止编译器提醒新增枚举变体。

### 次要问题：故障证据和超时范围

- `read_stream` 不保留 `event.host.observation` 的 transport、上游状态等事实；`execute` 又将读取故障简化成 message 并重建为 InvalidInput，样本只存 request_id 和错误文本。排查信息不足，需要独立修正。
- 所谓“单题 90 秒”目前只包住 `read_stream`；之前的 `execute_stream` 建立过程不在其中。宿主管理调用默认 120 秒，排队、建连或首次发送慢时可能先被父调用截止。此路径应报超时/中断，不会自行产生这条非 SSE 文案。
- 前端串行逐题调用，样本失败即 paused，用户 resume 后才继续；首轮未发送题优先于失败题重试。日志里连续失败的是不同题，不是同一题被自动请求四次。
- 正常 EOF 时宿主自动移除句柄；失败路径插件显式关闭。没有证据表明“成功流未 close”导致本次持续失败。

## 6. 建议修复与现场确认

### 修复优先级

1. **适配合法 Responses WebSocket 事件。** 在插件适配边界将完整、可解析的 WS JSON 事件交给同一 Responses 解析器；保留事件顺序及 error、refusal、failed、incomplete、completed 语义。`data=None` 时从完整 message 严格解析；未知非 JSON 文本明确报错，不能无条件伪装成 SSE 成功，也不能直接当成答案。继续消费至宿主 EOF，以完成资源及计费终态。
2. **分离非流式错误诊断。** 对 `RawJson`、`RawBody` 显示载荷类型及有界、脱敏的错误摘要；保留允许字段中的错误 code、上游状态、transport 和 request_id。不要把非流式错误塞入成功答案，不直接暴露完整正文、头或 credentials。仅补充异常文案不能解决第 1 项。
3. **补充真实合同回归。** 包括多批次 WS created/delta/completed、独立空 EOF、HTTP/WS 连续切换、WS 错误/截断/拒答、非 JSON WS、非流式错误和失败后继续；ARM/x86 发布冒烟使用同一组变体。

不要为此修改题目、推理强度、token 限制或失败计分规则，也不要用增加重试掩盖协议缺口。不建议回退到不兼容 v5 的旧插件。强制 HTTP 只能作为明确受支持的现场对照实验，不是长期修复；不能想当然向模型 body 加一个同名字段，宿主的传输控制与普通正文不是同一合同。

### 现场只需先补最有区分力的证据

由服务器使用者提供实际宿主版本及以下请求的脱敏详情：

- 最后成功：`req_01a16d349abf7603802fbcffa3b75915`
- 首次失败：`req_01a16d34a5de702bb4e83625cf544f7b`

字段：transport、transport decision、状态码、上游错误 code/message、最终状态。若可记录插件事件，再提供 wire kind/event，不需要完整响应正文或任何凭据。

- 成功为 HTTP、失败为 WebSocket：与已复现缺陷直接闭合。
- 失败为 RawJson/RawBody 且有明确 4xx/5xx：沿对应真实错误排查，WebSocket 缺口仍应修复。

修复后的发布验收：同一 ARM 环境实际完成 Meow 36 题与 ModelTrace 3 轮，核对宿主请求 ID、实际传输和成功/失败状态。真实计费请求由使用者明确触发。
