//! Python 发布夹具与真正 SDK 解码器共用一个固定样本，防止只测到自洽的模拟协议。
use gateway_plugin_sdk::call::{
    host::ModelEventBatch,
    model::{ExecutionEvent, WireEvent, WirePayload},
};
use serde_json::{Value, json};

#[test]
fn python_smoke_batch_decodes_with_the_pinned_sdk() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../scripts/tests/fixtures/model-events.json"
    ))
    .unwrap();
    let hex = fixture["batch_hex"].as_str().unwrap();
    let bytes: Vec<_> = (0..hex.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
        .collect();
    let decoded = ModelEventBatch::decode(&bytes).expect("Python GPE2 must satisfy SDK attach");
    let expected = fixture["payloads"].as_array().unwrap();
    assert_eq!(decoded.events.len(), expected.len());
    for (event, expected) in decoded.events.iter().zip(expected) {
        let expected: WirePayload = serde_json::from_value(expected.clone()).unwrap();
        assert!(event.wire.as_ref().unwrap().payload == expected);
    }
    // SDK 重新编码也必须保留完全相同的原始 wire；不要求 JSON 字段顺序一致。
    let encoded = decoded.encode().unwrap();
    assert!(
        ModelEventBatch::decode(&encoded).unwrap().events
            == ModelEventBatch::decode(&bytes).unwrap().events
    );
}

#[test]
fn inline_websocket_bytes_from_the_reviewed_commit_are_invalid_gpe2() {
    let event = ExecutionEvent::wire(WireEvent {
        protocol: "openai".into(),
        payload: WirePayload::WebSocket {
            event: None,
            data: Some(json!({"type":"response.completed"})),
            message: br#"{"type":"response.completed"}"#.to_vec(),
        },
    });
    let metadata = serde_json::to_vec(&event).unwrap();
    let mut broken = b"GPE2".to_vec();
    broken.extend_from_slice(&(metadata.len() as u32).to_be_bytes());
    broken.extend_from_slice(&[0; 8]);
    broken.extend_from_slice(&metadata);
    assert!(ExecutionEvent::decode(&broken).is_err());
    assert!(ExecutionEvent::decode(&event.encode().unwrap()).is_ok());
}
