# Chat 兼容基准 / Chat-compatible baselines

在“其他”类别选择 GPT 或 Claude 的 Chat 兼容版。站点不支持 Responses 或 Messages 时可使用，发往 `/chat/completions`。原生协议基准继续保留。

Choose the GPT or Claude Chat-compatible package under Other when an endpoint does not support Responses or Messages. Requests use `/chat/completions`; native packages remain available.

派生自4.5.3-predictive.3，沿用题目、128输出预算、配额、经验分布和强指向线。包内保留原始采集模式、原包摘要和原校准绑定；没有新增 Chat 协议实采，也未把旧采样标记为 Chat 采样。

Derived from4.5.3-predictive.3 without changing probes,128-token limits, allocations, empirical distributions or thresholds. Original collection mode, source digest and calibration binding are retained. No new Chat-protocol collection was performed.

Responses修复仅兼容成功完成时缺失/空数组output的情况，不支持将未完成、失败或拒绝的文本当成有效回答。事件定义参考[官方OpenAI文档](https://developers.openai.com/api/reference/resources/responses/streaming-events)。
