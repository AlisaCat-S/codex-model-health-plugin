# Responses 流修复：审查结论与最终方案

## 结论

`201dd76` 补上 WebSocket 变体的方向正确，但与 `394fd5a` 合并后仍不能直接作为发布候选：发布冒烟编码不符合 SDK，错误正文会泄漏到历史，且 JSON 重建会改变原始事件的严格解析结果。本次保留传输兼容目标，重写适配与诊断边界，并修正验收夹具。

修复前的源码对照和 2 成功 / 4 失败复现见 [原始调查](../stream-compatibility-audit-2026-10-24.md)。该调查基于 `6d07dff`；本文描述其后的最终实现。

## 两个提交的 review

### P1：发布冒烟生成了 SDK 拒绝的 WebSocket 事件

`201dd76:scripts/package-smoke.py` 把 `message` 字节数组放进 GPE2 元数据，却声明 wire 二进制段长度为 0。SDK `call/model/codec.rs::attach` 要求元数据中的该数组为空，再从独立 wire 段恢复字节，因此第二次模型请求就会出现“模型事件批次格式错误”。Rust 单测使用 SDK 自己的 encode，无法暴露 Python 夹具的这项错误。

已用 `inline_websocket_bytes_from_the_reviewed_commit_are_invalid_gpe2` 复现旧编码被锁定 SDK 拒绝。修复后，Python 编码和 Rust SDK 共同验证一个固定二进制样本，覆盖 JSON、SSE、带/不带 JSON 视图的 WS、RawJson 和 RawBody。

### P1：异常摘录不是脱敏，会把敏感正文写进检测历史

`394fd5a` 的 RawJson 错误 `code/message` 直接拼接；RawBody 及 `201dd76` 的非 JSON WS 路径直接摘录原文。上游回显的 Token、Cookie 或其他私有内容因此可能进入页面和持久化 runs。截取 120/200/512 字节不能消除此风险，RawJson 分支也没有在诊断构造处限长。

改为不保存这些载荷原文：保留载荷类型、字节数、宿主观测中的已知 transport 和 HTTP 状态，以及原有 request_id。详细正文由操作者按请求 ID 在宿主侧查阅。宿主 PluginFault 的公开 code、http_status、send_state 可以保存，details 不落入历史。

### P2：优先使用解析视图并重新序列化会抹掉异常

`201dd76:backend/src/host.rs` 使用 `data.or_else(parse(message))`，之后把 Value 序列化成 SSE。两条路径都会丢失重复 JSON 字段；例如先有 `type:error`、后有 `type:response.completed` 的重复字段可能只剩 completed，而原 Meow 严格解析器应拒绝这个事件。其 WS created 测试还使用了与 raw message 不一致的 data 视图。

新实现以完整 WS message 为输入，借用 `serde_json::value::RawValue` 校验 JSON 语法和对象形态，不生成或合并 JSON 树；原始字段仍交由 Python 严格解析。原生 SSE 字节也优先保留。错误、拒答、incomplete、截断仍由同一解析器判断，不改变题目或评分。

### P2：流结束与诊断分类需要补齐

原执行代码在所有失败后都 close；但 `end=true` 已表示宿主回收句柄，即使同批载荷解析失败也不应再 close。原代码还把宿主错误降成一个 InvalidInput message，丢掉真实分类、状态码和发送事实。

现记录宿主 EOF，仅未结束的失败流 close 一次；保持原 PluginFault，超时使用 Timeout。本地批次解码失败使用 Fault，并记录发送状态为 Ambiguous，避免默认 NotSent 错误暗示请求未发送。成功仍持续读取到宿主 EOF，而不是见到 response.completed 就提前返回。

### P2：测试环境与调查叙述不够准确

自动按 `docker --version` 选择系统 Python 会使不同机器运行不同环境，也不能识别“CLI 已装但 daemon 不可用”。本地 Python 改为 `MODEL_HEALTH_TEST_PYTHON` 显式选择；未设置时保持原 Docker 路径，发布构建仍使用内嵌引擎。

“连接入池后所有后续题必走同一条 WS”没有现场证据；不同题可能有不同会话池键。已确认的是正常 WS 被旧插件拒绝，现场是否恰好从 HTTP 切到 WS 需日志确认。该缺陷可在 x86_64 复现；ARM 制品兼容性仍需独立运行验收。

## 最终实现

### 一个传输适配器，一个评分解析器

`backend/src/host/responses.rs::ResponsesStream` 集中处理 SDK 的全部 wire 变体：

- Json 有 raw_sse 时保留原始 SSE；只有 data 时维持原来的 JSON 适配。
- RawSse 校验 UTF-8 后保持原文。
- WebSocket 使用完整 UTF-8 JSON 对象文本；逐行添加 SSE data 前缀，支持缩进、CRLF 和中文。可选 data 不替代原始消息。
- RawJson / RawBody 明确失败，不当成回答。
- 无 wire 的观测事件更新安全诊断；不生成虚假的完成事件。

使用穷尽 match，使未来 SDK 新增变体在编译期要求适配。主缓冲区在追加前检查累计 1 MiB 上限，不先写入超限内容；没有对同一 JSON 树进行解析后再序列化的开销。关键协议约定在代码旁以中文注释说明。

`host.rs` 只负责回调、批次解码、EOF 与回收。失败样本保留 request_id，并新增可选 error_code/http_status/send_state；旧历史无需迁移。报告仍只统计 status=ok 的样本，失败仍暂停并消耗一次预算。

### 发布测试使用真实二进制格式

`scripts/model_stream_fixture.py` 编码 HME1 批次与 GPE2 事件，原始字节移入 wire 二进制段。`package-smoke.py` 逐次轮换 Json、带视图 WS、仅文本 WS、RawSse，并分批发送 created / delta / completed / 空 EOF。

`scripts/tests/fixtures/model-events.json` 同时供 Python 编码测试与 `backend/tests/smoke_codec.rs` 的 SDK 解码测试使用；两侧都通过才证明夹具符合锁定版本。构建脚本在打包前运行 Python 夹具测试，Rust 检查随原有 bundled-engine 测试运行，不增加发布环境的 Python 依赖。

## 验证与运行方式

本机使用 Windows x86_64、Rust 1.99.1、Python 3.13.7 / NumPy 2.5.1。验证结果：42 个 Rust 测试通过（13 个单元测试、27 个协议集成测试、2 个跨语言编码测试），2 个 Python 测试通过；Clippy `-D warnings`、Rust 格式检查、前端类型检查及 Python/Bash 语法检查通过。

新增和调整的协议测试覆盖：

- HTTP 成功两次后 WS 连续成功四次；各封套的回答与 usage 一致。
- 多批次、独立 EOF、终态与载荷同批、避免重复关闭；错误批次不标为未发送。
- 空流、只有 delta、error、failed、incomplete、refusal、成功事件之后再出错。
- 非 JSON、非对象、非法 UTF-8、重复字段、data 与原消息不一致；中文及缩进 CRLF 正常解析。
- 非流式错误不回显敏感正文，安全观测单独成帧，宿主错误事实保留。
- 累计超限仅关闭一次，失败后显式恢复，失败样本不评分。
- 既有完整 36 题、ModelTrace、账号绑定、状态恢复及更新接口测试。

Windows 本地测试（指定已安装 NumPy 的 Python 可执行文件）：

```powershell
$env:MODEL_HEALTH_TEST_PYTHON='C:/Python313/python.exe'
cargo test --locked --manifest-path backend/Cargo.toml
cargo clippy --locked --manifest-path backend/Cargo.toml --all-targets -- -D warnings
python -X utf8 -B -m unittest discover -s scripts/tests -v
pnpm --dir frontend typecheck
```

Linux/macOS 使用 `MODEL_HEALTH_TEST_PYTHON=/path/to/python3 cargo test --locked --manifest-path backend/Cargo.toml`。未设置变量时仍需原 Docker 测试镜像；这些选择只影响开发测试，不影响发布包的内嵌引擎。

本次不扩展超时策略：90 秒限制的是模型流读取阶段，不含此前 execute_stream 建立过程；宿主管理调用另有整体期限。文案和 README 已按实际范围说明。

## 发布前仍需执行的验收

本机没有 Docker，未运行 Linux x86/ARM 安装包容器冒烟，也未进行真实计费检测。代码层和跨语言编解码验证不替代这两项。

1. 发布负责人通过现有构建流程分别构建 x86_64 与 aarch64，完成真实内嵌引擎及安装包冒烟；不要只以 cargo check 作为运行验收。
2. 使用者在 ARM 宿主主动执行 Meow 36 题与 ModelTrace 3 轮，核对宿主 request_id、transport、状态与插件样本。
3. 若仍有错误，先按 request_id 检查宿主实际状态；不要增加自动重试、降低评分标准或重置历史。
