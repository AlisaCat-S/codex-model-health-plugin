# 创建检测后 KeyError 与详情打不开

## 复现与原因

现场版本为插件 `0.3.0-20261026.1136`（提交 `920cba6`）、宿主 `v3.34.0`。使用该插件提交的 `engine.rs` 与真实 Python worker，可离线复现以下顺序：

1. `catalog` 请求发送后，取消等待它的父调用
2. 旧引擎保留子进程，`prepare` 读到上一次的 catalog 响应
3. `score` 又读到 prepare 响应；创建流程将 catalog 保存为 plan、将 plan 保存为 report
4. 下一次引擎查询收到 `检测引擎：KeyError`

这种记录的计划没有 `request_model`、`tier`、`jobs`，对应列表中的空模型、空档位。详情模板直接读取 `plan.jobs.length`，引起渲染错误，无法正常打开和控制任务。

已核对宿主 `v3.33.0` 与 `v3.34.0` 的 RPC 帧和私有状态读写合同：没有导致上述形态变化的格式差异。旧插件自身即可复现该故障，无需回退宿主。现场具体是哪次父调用触发了取消，需要对应日志才能确认。

## 当前处理

- 取消中的引擎查询会丢弃子进程，迟到响应不再交给下一次查询（`f2285bd` 已包含此修正）
- 新建任务落盘前校验计划与报告结构，拒绝将错位响应保存为任务
- 列表及详情返回动态 `data_error`，不重写原始计划、报告或请求明细
- 未完成的异常任务暂停且退出队列；拒绝续测，仍可查看和结束，不阻塞其他任务
- 页面以“记录异常”显示这些任务，详情不再访问缺失的计划或报告字段

异常计划缺少原始题目和采样配置，不能自动重建后混入原任务。升级插件后，打开异常记录，结束任务，再新建检测；已有历史及请求 ID 保留。更新同一插件，不要通过卸载删除私有数据。

## 回归入口

- `backend/tests/engine_cancellation.rs::cancelled_catalog_cannot_be_saved_as_the_next_run_plan`：取消 catalog 后，真实 worker 的 prepare、score、payload 响应仍对应各自请求
- `backend/tests/protocol.rs::shifted_legacy_plan_is_readable_and_stoppable_without_a_healthy_engine`：旧错位记录可读取、结束、重开；不依赖评分引擎，不发送模型请求
- `backend/tests/protocol.rs::malformed_report_keeps_existing_request_details_available`：报告为空时保留已有请求明细
- `scripts/recovery-browser-qa.mjs`：列表到详情、结束、刷新重开、请求 ID、窄屏，以及随后新建正常任务

## 本地验证结果

Windows 本地 Python 路径下，Rust 的 13 项单元测试、2 项引擎取消测试、42 项协议测试、5 项 SDK 兼容测试和 3 项编码测试通过；Clippy `-D warnings` 通过。前端 7 项单元测试、生产构建、正常流程与异常记录的两组浏览器交互检查通过，已查看桌面和窄屏截图。

上述回归均为离线模拟宿主或本地 worker，不产生真实计费请求。本机没有 Docker，未执行 Linux 内嵌引擎打包及服务器安装验收；发布时仍需运行 `scripts/build-linux.sh` 中的构建和安装包冒烟流程。

发布流程已修正取消回归测试的执行环境：Rust 容器显式安装并选择系统 Python、NumPy、HTTPX 运行脚本夹具，避免在容器内再次调用不存在的 Docker。此前 `f2285bd` 的两个架构构建均在该测试失败，因此没有产出新版 Release。协议测试和发布安装包仍使用固定依赖构建的内嵌引擎。
