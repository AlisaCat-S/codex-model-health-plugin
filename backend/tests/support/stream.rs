use super::*;
use gateway_plugin_sdk::call::model::facts::{ExecutionFacts, ResponseObservation};

pub(super) fn wire(payload: WirePayload) -> ExecutionEvent {
    ExecutionEvent::wire(WireEvent {
        protocol: "openai".into(),
        payload,
    })
}

pub(super) fn json_wire(data: Value) -> WirePayload {
    WirePayload::Json {
        event: None,
        data,
        id: None,
        retry: None,
        raw_sse: None,
    }
}

fn completed() -> Value {
    json!({"type":"response.completed","response":{"id":"response-one","status":"completed",
        "output":[{"type":"message","role":"assistant","content":[{"type":"output_text","text":"3"}]}],
        "usage":{"input_tokens":10,"output_tokens":1}}})
}

fn websocket(data: Value, parsed: bool) -> WirePayload {
    WirePayload::WebSocket {
        event: data["type"].as_str().map(str::to_owned),
        message: serde_json::to_string_pretty(&data)
            .unwrap()
            .replace('\n', "\r\n")
            .into_bytes(),
        data: parsed.then_some(data),
    }
}

fn script(host: &mut Host, payloads: Vec<WirePayload>) {
    host.model_events = Some(payloads.into_iter().map(wire).collect());
}

async fn step(peer: &mut Peer, host: &mut Host, run: &Value) -> Value {
    peer.api("api/runs/step", Some(json!({"id":run["id"]})), host)
        .await
        .unwrap()["run"]
        .clone()
}

fn closes(host: &Host) -> usize {
    host.callbacks
        .iter()
        .filter(|method| *method == "host.model.stream_close")
        .count()
}

#[tokio::test]
async fn all_native_envelopes_preserve_answers_and_drain_to_eof() {
    let mut data = completed();
    data["response"]["output"][0]["content"][0]["text"] = json!("加拿大");
    let raw = format!("data: {data}\n\n").into_bytes();
    let variants = [
        json_wire(data.clone()),
        WirePayload::RawSse { frame: raw.clone() },
        WirePayload::Json {
            data: data.clone(),
            event: None,
            id: None,
            retry: None,
            raw_sse: Some(raw),
        },
        websocket(data.clone(), true),
        websocket(data, false),
    ];
    let mut peer = Peer::new().await;
    let mut host = Host::default();
    let run = peer.start(&mut host).await;
    for (index, payload) in variants.into_iter().enumerate() {
        script(&mut host, vec![payload]);
        let result = step(&mut peer, &mut host, &run).await;
        assert_eq!(result["attempts"][index]["answer"], "加拿大");
        assert_eq!(result["attempts"][index]["usage"]["input_tokens"], 10);
        assert_eq!(result["report"]["valid_samples"], index + 1);
        assert!(!host.model_open);
    }
    assert_eq!(closes(&host), 0);
    assert_eq!(
        host.callbacks
            .iter()
            .filter(|m| *m == "host.model.stream_read")
            .count(),
        10
    );
}

#[tokio::test]
async fn two_http_successes_then_four_websocket_successes() {
    let mut peer = Peer::new().await;
    let mut host = Host::default();
    let run = peer.start(&mut host).await;
    for index in 0..6 {
        if index >= 2 {
            script(
                &mut host,
                vec![
                    websocket(
                        json!({"type":"response.created","response":{"id":"response-one"}}),
                        true,
                    ),
                    websocket(
                        json!({"type":"response.output_text.delta","delta":"3"}),
                        false,
                    ),
                    websocket(completed(), true),
                ],
            );
        }
        let result = step(&mut peer, &mut host, &run).await;
        assert_eq!(result["status"], "ready");
        assert_eq!(result["report"]["valid_samples"], index + 1);
        assert_eq!(
            result["attempts"][index]["request_id"],
            format!("request-{}", index + 1)
        );
    }
    assert_eq!(closes(&host), 0);
}

#[tokio::test]
async fn websocket_failures_never_score_partial_or_previous_answers() {
    let cases = [
        (vec![], "truncated_stream"),
        (
            vec![json!({"type":"response.output_text.delta","delta":"3"})],
            "truncated_stream",
        ),
        (
            vec![
                completed(),
                json!({"type":"error","error":{"code":"rate_limit_exceeded"}}),
            ],
            "upstream_stream_error",
        ),
        (
            vec![json!({"type":"response.failed","response":{"error":{"code":"server_error"}}})],
            "upstream_response_failed",
        ),
        (
            vec![
                json!({"type":"response.incomplete","response":{"incomplete_details":{"reason":"max_output_tokens"}}}),
            ],
            "response_token_limit",
        ),
        (
            vec![json!({"type":"response.refusal.done"})],
            "response_refused",
        ),
    ];
    for (events, expected) in cases {
        let mut peer = Peer::new().await;
        let mut host = Host::default();
        let run = peer.start(&mut host).await;
        script(
            &mut host,
            events
                .into_iter()
                .map(|event| websocket(event, true))
                .collect(),
        );
        let failed = step(&mut peer, &mut host, &run).await;
        assert_eq!(failed["status"], "paused");
        assert_eq!(failed["report"]["valid_samples"], 0);
        assert_eq!(failed["attempts"][0]["error"], expected);
        assert_eq!(closes(&host), 0, "semantic errors are evaluated after EOF");
        // 失败仍消耗一次尝试；显式恢复后可以继续，不留下租约或流句柄。
        peer.api(
            "api/runs/control",
            Some(json!({"id":run["id"],"action":"resume"})),
            &mut host,
        )
        .await
        .unwrap();
        let resumed = step(&mut peer, &mut host, &run).await;
        assert_eq!(resumed["attempts"].as_array().unwrap().len(), 2);
        assert_eq!(resumed["report"]["valid_samples"], 1);
    }
}

#[tokio::test]
async fn websocket_raw_message_is_authoritative_and_errors_do_not_echo_it() {
    let duplicate = format!("{{\"type\":\"error\",{}", &completed().to_string()[1..]);
    for (message, expected, expected_closes) in [
        (b"token=fixture-secret".to_vec(), "WebSocket JSON", 1),
        (vec![0xff], "UTF-8", 1),
        (b"[]".to_vec(), "不是对象", 1),
        (duplicate.into_bytes(), "invalid_stream", 0),
    ] {
        let mut peer = Peer::new().await;
        let mut host = Host::default();
        let run = peer.start(&mut host).await;
        // 即使解析视图看似成功，原始消息也不能被替换或经 Value 合并重复字段。
        script(
            &mut host,
            vec![WirePayload::WebSocket {
                event: None,
                data: Some(completed()),
                message,
            }],
        );
        let result = step(&mut peer, &mut host, &run).await;
        assert_eq!(result["status"], "paused");
        assert_eq!(result["report"]["valid_samples"], 0);
        assert!(
            result["attempts"][0]["error"]
                .as_str()
                .unwrap()
                .contains(expected)
        );
        assert!(!result.to_string().contains("fixture-secret"));
        assert_eq!(closes(&host), expected_closes);
    }
}

#[tokio::test]
async fn non_streaming_errors_keep_safe_observations_not_body_or_headers() {
    for (payload, kind) in [
        (
            WirePayload::RawJson {
                body:
                    br#"{"error":{"code":"sk-fixture-secret","message":"Bearer fixture-secret"}}"#
                        .to_vec(),
            },
            "RawJson",
        ),
        (
            WirePayload::RawBody {
                body: b"Set-Cookie: fixture-secret".to_vec(),
            },
            "RawBody",
        ),
    ] {
        let mut peer = Peer::new().await;
        let mut host = Host::default();
        let run = peer.start(&mut host).await;
        let mut observation = ResponseObservation::new("http_json");
        observation.status_code = Some(429);
        observation.provider_metadata = Some("fixture-secret".into());
        host.model_events = Some(
            vec![
                ExecutionEvent {
                    host: Some(Box::new(ExecutionFacts {
                        observation: Some(observation),
                        ..Default::default()
                    })),
                    ..Default::default()
                },
                wire(payload),
            ]
            .into(),
        );
        let result = step(&mut peer, &mut host, &run).await;
        let sample = &result["attempts"][0];
        let error = sample["error"].as_str().unwrap();
        assert!(error.contains(kind) && error.contains("HTTP 429") && error.contains("http_json"));
        assert_eq!(sample["http_status"], 429);
        assert_eq!(sample["error_code"], "upstream");
        assert_eq!(sample["send_state"], "ambiguous");
        assert!(!result.to_string().contains("fixture-secret"));
        assert_eq!(result["report"]["valid_samples"], 0);
        assert_eq!(closes(&host), 1);
    }
}

#[tokio::test]
async fn terminal_batch_is_not_closed_twice_even_when_payload_is_invalid() {
    for payload in [
        websocket(completed(), false),
        WirePayload::RawBody { body: vec![] },
    ] {
        let mut peer = Peer::new().await;
        let mut host = Host {
            end_with_last: true,
            ..Default::default()
        };
        let run = peer.start(&mut host).await;
        script(&mut host, vec![payload]);
        step(&mut peer, &mut host, &run).await;
        assert!(!host.model_open);
        assert_eq!(closes(&host), 0);
    }
}

#[tokio::test]
async fn aggregate_limit_closes_once_and_does_not_score_partial_output() {
    let mut peer = Peer::new().await;
    let mut host = Host::default();
    let run = peer.start(&mut host).await;
    // 每帧小于 stream_read 的 256 KiB，总响应越过 1 MiB；不能只限制单帧。
    let delta = json!({"type":"response.output_text.delta","delta":"x".repeat(200_000)});
    script(
        &mut host,
        (0..6).map(|_| websocket(delta.clone(), false)).collect(),
    );
    let result = step(&mut peer, &mut host, &run).await;
    assert_eq!(result["report"]["valid_samples"], 0);
    assert!(
        result["attempts"][0]["error"]
            .as_str()
            .unwrap()
            .contains("1 MiB")
    );
    assert_eq!(closes(&host), 1);
    assert!(!host.model_open);
}

#[tokio::test]
async fn invalid_host_batches_do_not_claim_the_request_was_unsent() {
    for (state, payload, expected_closes) in [
        (json!({}), vec![], 1),
        (json!({"events":1,"end":false}), b"broken GPE2".to_vec(), 1),
        (json!({"events":1,"end":true}), b"broken GPE2".to_vec(), 0),
        (
            json!({"events":1,"end":true}),
            ModelEventBatch::default().encode().unwrap(),
            0,
        ),
    ] {
        let mut peer = Peer::new().await;
        let mut host = Host::default();
        let run = peer.start(&mut host).await;
        host.model_read_reply = Some((state, payload));
        let result = step(&mut peer, &mut host, &run).await;
        assert_eq!(result["status"], "paused");
        assert_eq!(result["report"]["valid_samples"], 0);
        let sample = &result["attempts"][0];
        assert_eq!(sample["request_id"], "request-1");
        assert_eq!(sample["error_code"], "fault");
        assert_eq!(sample["send_state"], "ambiguous");
        assert_eq!(closes(&host), expected_closes);
        assert!(!host.model_open);
    }
}
