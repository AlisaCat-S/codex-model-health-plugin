//! 将宿主原生 Responses 事件交给同一个 Meow 解析器；不在传输适配层判定回答成功。

use gateway_plugin_sdk::{
    ErrorCode, PluginFault,
    call::model::{ExecutionEvent, WirePayload},
};
use serde_json::value::RawValue;

const MAX_RESPONSE_BYTES: usize = 1024 * 1024;

#[derive(Default)]
pub(super) struct ResponsesStream {
    sse: String,
    transport: Option<&'static str>,
    status: Option<u16>,
}

impl ResponsesStream {
    pub(super) fn push(&mut self, event: ExecutionEvent) -> Result<(), PluginFault> {
        // 观测可能单独成帧；仅保留明确的非秘密字段，不复制头、正文或 provider_metadata。
        if let Some(observation) = event.host.and_then(|host| host.observation) {
            self.transport = match observation.transport.as_str() {
                "http_sse" => Some("http_sse"),
                "http_json" => Some("http_json"),
                "websocket" => Some("websocket"),
                _ => None,
            };
            self.status = observation.status_code;
        }
        let Some(wire) = event.wire else {
            return Ok(());
        };
        if wire.protocol != "openai" {
            return Err(self.fault("模型返回了不匹配的协议"));
        }
        // 穷尽匹配：SDK 新增变体必须在升级时审查，不能再次被兜底分支悄悄拒绝。
        match wire.payload {
            WirePayload::Json {
                raw_sse: Some(frame),
                ..
            }
            | WirePayload::RawSse { frame } => {
                let text = std::str::from_utf8(&frame)
                    .map_err(|_| self.fault("模型返回了无效的 UTF-8 SSE 帧"))?;
                self.append(text)
            }
            WirePayload::Json {
                data,
                raw_sse: None,
                ..
            } => self.append_event(&data.to_string()),
            WirePayload::WebSocket { message, .. } => {
                // v5 的 message 是完整原始 WS 文本，data 只是可选解析视图。
                // 不重建 JSON：否则重复字段会被 serde_json::Value 合并，绕过 Python 的严格校验。
                let text = std::str::from_utf8(&message)
                    .map_err(|_| self.fault("模型返回了无效的 UTF-8 WebSocket 消息"))?;
                let raw: &RawValue = serde_json::from_str(text)
                    .map_err(|_| self.fault("模型返回了无效的 WebSocket JSON 事件"))?;
                if !raw.get().starts_with('{') {
                    return Err(self.fault("模型返回的 WebSocket JSON 事件不是对象"));
                }
                self.append_event(raw.get())
            }
            WirePayload::RawJson { body } => Err(self.non_streaming("RawJson", body.len())),
            WirePayload::RawBody { body } => Err(self.non_streaming("RawBody", body.len())),
        }
    }

    fn append_event(&mut self, text: &str) -> Result<(), PluginFault> {
        // WS JSON 可以缩进或换行；每行都加 data:，防止原文换行成为额外 SSE 帧。
        for line in text.split(['\r', '\n']) {
            self.append("data: ")?;
            self.append(line)?;
            self.append("\n")?;
        }
        self.append("\n")
    }

    fn append(&mut self, text: &str) -> Result<(), PluginFault> {
        if text.len() > MAX_RESPONSE_BYTES - self.sse.len() {
            return Err(self.fault("检测响应超过 1 MiB"));
        }
        self.sse.push_str(text);
        Ok(())
    }

    fn non_streaming(&self, kind: &str, bytes: usize) -> PluginFault {
        // 上游错误可能回显凭据；截断不是脱敏。正文留在宿主，页面用请求 ID 关联详情。
        self.fault(&format!(
            "模型返回非流式正文（{kind}，{bytes} 字节）；请按请求 ID 查看宿主详情"
        ))
    }

    fn fault(&self, message: &str) -> PluginFault {
        let mut fault = super::stream_fault(ErrorCode::Upstream, message);
        fault.http_status = self.status;
        if let Some(transport) = self.transport {
            fault.message.push_str(&format!("；传输 {transport}"));
        }
        if let Some(status) = self.status {
            fault.message.push_str(&format!("；HTTP {status}"));
        }
        fault
    }

    pub(super) fn finish(self) -> String {
        self.sse
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use gateway_plugin_sdk::call::model::WireEvent;

    fn wire(payload: WirePayload) -> ExecutionEvent {
        ExecutionEvent::wire(WireEvent {
            protocol: "openai".into(),
            payload,
        })
    }

    #[test]
    fn raw_json_spelling_and_duplicate_fields_survive_adaptation() {
        let message = br#"{"type":"error","type":"response.completed"}"#.to_vec();
        let mut stream = ResponsesStream::default();
        stream
            .push(wire(WirePayload::WebSocket {
                event: None,
                data: Some(serde_json::json!({"type":"response.completed"})),
                message: message.clone(),
            }))
            .unwrap();
        assert_eq!(
            stream.finish(),
            format!("data: {}\n\n", String::from_utf8(message).unwrap())
        );
    }

    #[test]
    fn response_limit_is_checked_before_extending_the_buffer() {
        let mut stream = ResponsesStream::default();
        stream.append(&"x".repeat(MAX_RESPONSE_BYTES)).unwrap();
        assert!(stream.append("x").is_err());
        assert_eq!(stream.sse.len(), MAX_RESPONSE_BYTES);
    }

    #[test]
    fn non_streaming_body_is_never_in_the_diagnostic() {
        for payload in [
            WirePayload::RawBody {
                body: b"Authorization: Bearer fixture-secret".to_vec(),
            },
            WirePayload::RawJson {
                body: br#"{"error":{"message":"token=fixture-secret"}}"#.to_vec(),
            },
        ] {
            let error = ResponsesStream::default().push(wire(payload)).unwrap_err();
            assert!(!error.message.contains("fixture-secret"));
            assert!(error.message.len() < 512);
        }
    }
}
