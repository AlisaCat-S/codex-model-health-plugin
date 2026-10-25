# 自动构建发布说明（Issue #1）

`.github/workflows/release.yml` 负责自动构建与发布，本文记录其设计、版本号规则与本地验证方式。

## 触发与发布行为

| 触发 | 行为 |
| --- | --- |
| 推送 `main` | 自动构建双架构并创建正式 Release（标记 latest） |
| 手动 `workflow_dispatch`（任意分支） | 同上；勾选 `dry_run` 则只构建与离线验收、不创建 Release，适合在分支试跑 |

并发控制：同一 ref 的新运行排队（`cancel-in-progress: false`），不会中途打断已开始的发布。

## 版本号规则（时间命名）

- 格式：`v<语义版本>-<yyyymmdd>.<HM>`，如 `v0.2.2-20261024.1503`；05:04 记为 `20261024.504`。
- 分钟段按十进制去掉前导零：宿主 SDK 用 `semver::Version` 解析清单版本，而 semver 要求数字标识符不得以前导零开头（`0504` 非法，`504` 合法）；`0`（00:00）合法。去零后按数值比较仍严格单调（59 < 100 < 2359）。
- 语义版本取自 `plugin.json` 的 `version`（若含预发布后缀则取 `-` 之前部分），由维护者手工推进；时间戳为流水线启动时刻的 **UTC** `yyyymmdd.HHMM`，每次运行不同。
- 该格式是合法 semver 预发布版本：同一语义版本下时间越大版本越新，且始终小于下一个语义版本，宿主升级比较不受影响。
- 版本号在构建时注入工作区的 `plugin.json`、`backend/Cargo.toml` 与 `Cargo.lock`（插件 User-Agent 使用 `CARGO_PKG_VERSION`，需与清单一致；lock 同步更新以维持 `--locked`），均**不回写仓库**；提交历史中的 `plugin.json` 始终保留纯语义版本。

## 双架构构建

| 制品 | runner | 引擎 | Rust 二进制 | 冒烟验收容器 |
| --- | --- | --- | --- | --- |
| `x86_64-unknown-linux-gnu` | `ubuntu-latest` | `docker buildx --platform linux/amd64`（原生） | `rust:1.99-slim-bookworm` 容器内原生构建 | `--platform linux/amd64` |
| `aarch64-unknown-linux-gnu` | `ubuntu-24.04-arm` | `docker buildx --platform linux/arm64`（原生） | 同上（arm64 原生） | `--platform linux/arm64` |

仓库为公开仓库，GitHub 提供免费的 arm64 托管 runner，因此无需 QEMU 模拟或交叉工具链，两个架构均为原生构建，与既有本地构建命令保持一致（glibc/Debian 12 基线不变）。

打包 CLI 与 SDK 同源锁定：`cargo install codex-proxy-plugin-cli --rev 06e1d8f0ac33d8633198d837c4f9017ad466f358 --locked`（v3.31.1，插件 RPC 协议 v5），在对应架构的 `rust:1.99-slim-bookworm` 容器内安装，产物为该架构原生二进制。

## 权限

- 顶层默认 `permissions: contents: read`。
- 仅 `release` 作业提升为 `contents: write`（创建 Release、上传制品）。
- 使用内置 `GITHUB_TOKEN`，不引入第三方 PAT。

## 本地验证

```sh
bash -n scripts/build-linux.sh          # 脚本语法
./scripts/build-linux.sh                # 本地默认 x86_64 全流程（需 Docker/Node 24+/pnpm 12.14/Python 3.9+）
./scripts/build-linux.sh aarch64-unknown-linux-gnu   # ARM64 包（在 ARM 机器上原生；x86 机器上需 QEMU）
actionlint .github/workflows/release.yml  # workflow 静态校验
```

`scripts/package-smoke.py` 的验收容器平台默认 `linux/amd64`，可用环境变量 `SMOKE_PLATFORM=linux/arm64` 覆盖（`build-linux.sh` 已按目标自动设置）。
