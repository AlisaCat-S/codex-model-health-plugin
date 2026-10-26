//! Multi-call host: maintenance stays alive while page calls come and go.
use super::*;

#[derive(Default)]
struct Schedule {
    epoch: u64,
    suspended: bool,
    resident: BTreeSet<u64>,
}
struct Background {
    peer: Peer,
    id: u64,
    calls: BTreeMap<u64, Schedule>,
}

impl Background {
    async fn new(mut peer: Peer, timeout_ms: u64) -> Self {
        let id = peer.sequence;
        peer.sequence += 2;
        peer.send(Frame::control(Message::Call {
            id,
            method: "plugin.reconcile".into(),
            params: json!({}),
            context: CallContext {
                request: None,
                call_id: id,
                instance_id: "test".into(),
                generation: 1,
                incarnation: "test".into(),
                stage: Stage::Maintenance,
                timeout_ms,
                resource_stream: false,
                resource_scope_id: "maintenance".into(),
                request_id: None,
                attempt_id: None,
                account_id: None,
                credential_revision: None,
            },
        }))
        .await;
        Self {
            peer,
            id,
            calls: BTreeMap::new(),
        }
    }
    async fn tick(&mut self, host: &mut Host) -> Option<(u64, Result<Value, PluginFault>)> {
        let frame = self.peer.receive().await;
        match frame.message {
            Message::Callback {
                id,
                parent_id,
                method,
                params,
            } => {
                let s = self.calls.entry(parent_id).or_default();
                assert!(!s.suspended && s.resident.insert(id));
                if method.starts_with("host.model.") {
                    assert_eq!(parent_id, self.id);
                }
                let response = match host.callback(&method, params, frame.payload) {
                    Ok((result, payload)) => Frame {
                        message: Message::Result { id, result },
                        payload,
                    },
                    Err(error) => Frame::control(Message::Error { id, error }),
                };
                self.peer.send(response).await;
            }
            Message::Suspend { id, epoch } => {
                let s = self.calls.entry(id).or_default();
                assert!(!s.suspended);
                assert_eq!(epoch, s.epoch + 1);
                s.epoch = epoch;
                s.suspended = true;
            }
            Message::Resume { id, epoch } => {
                let s = self.calls.get_mut(&id).unwrap();
                assert!(s.suspended);
                assert_eq!(epoch, s.epoch);
                self.peer
                    .send(Frame::control(Message::Resumed { id, epoch }))
                    .await;
                s.suspended = false;
            }
            Message::CallbackConsumed { id, parent_id } => {
                let s = self.calls.get_mut(&parent_id).unwrap();
                assert!(!s.suspended && s.resident.remove(&id));
            }
            Message::Result { id, result } => {
                let s = self.calls.remove(&id).unwrap_or_default();
                assert!(!s.suspended && s.resident.is_empty());
                let body = if frame.payload.is_empty() {
                    result.clone()
                } else {
                    serde_json::from_slice(&frame.payload).unwrap()
                };
                if result["status"].as_u64().is_some_and(|s| s >= 400) {
                    return Some((
                        id,
                        Err(serde_json::from_value(body["error"].clone()).unwrap()),
                    ));
                }
                return Some((id, Ok(body)));
            }
            Message::Error { id, error } => return Some((id, Err(error))),
            Message::Cancelled { id } => return Some((id, Ok(Value::Null))),
            other => panic!("unexpected background frame {other:?}"),
        }
        None
    }
    async fn until(&mut self, host: &mut Host, done: impl Fn(&Host) -> bool) {
        while !done(host) {
            assert!(
                self.tick(host).await.is_none(),
                "maintenance ended unexpectedly"
            );
        }
    }
    async fn api(
        &mut self,
        path: &str,
        input: Option<Value>,
        host: &mut Host,
    ) -> Result<Value, PluginFault> {
        let id = self.peer.begin_api(path, input).await;
        loop {
            if let Some((finished, result)) = self.tick(host).await {
                assert_eq!(finished, id);
                return result;
            }
        }
    }
    async fn finish(&mut self, host: &mut Host) -> Result<Value, PluginFault> {
        loop {
            if let Some((id, result)) = self.tick(host).await {
                assert_eq!(id, self.id);
                return result;
            }
        }
    }
    async fn cancel(mut self, host: &mut Host) -> Peer {
        self.peer
            .send(Frame::control(Message::Cancel { id: self.id }))
            .await;
        self.finish(host).await.unwrap();
        // Real host cancellation reclaims this parent's streams.
        host.model_open = false;
        host.model_events = None;
        self.peer
    }
}
async fn queued(peer: &mut Peer, host: &mut Host) -> Value {
    peer.api("api/runs/start",Some(json!({"background":true,"account_id":"account-b","key_id":"key-b","request_model":"gpt-6-astra","claimed_model":"gpt-6-astra","tier":"low"})),host).await.unwrap()["run"].clone()
}
fn saved<'a>(host: &'a Host, id: &Value) -> &'a Value {
    &host.state.values().find(|(r, _)| r["id"] == *id).unwrap().0
}

#[tokio::test]
async fn finishes_without_page_steps_and_reopens_completed() {
    let mut peer = Peer::new().await;
    let mut host = Host::default();
    let run = queued(&mut peer, &mut host).await;
    assert!(host.executions.is_empty());
    assert!(
        peer.api("api/runs/step", Some(json!({"id":run["id"]})), &mut host)
            .await
            .unwrap_err()
            .message
            .contains("后台托管")
    );
    let mut bg = Background::new(peer, 3_600_000).await;
    bg.until(&mut host, |h| saved(h, &run["id"])["status"] == "completed")
        .await;
    assert_eq!(host.executions.len(), 36);
    assert_eq!(saved(&host, &run["id"])["report"]["valid_samples"], 36);
    assert!(!host.model_open && !host.callbacks.iter().any(|m| m.starts_with("host.http.")));
    let reopened = bg
        .api("api/runs/get", Some(json!({"id":run["id"]})), &mut host)
        .await
        .unwrap();
    assert_eq!(reopened["run"]["status"], "completed");
    bg.cancel(&mut host).await;
}

#[tokio::test]
async fn pause_preserves_inflight_and_resume_queues_at_tail() {
    let mut peer = Peer::new().await;
    let mut host = Host::default();
    let first = queued(&mut peer, &mut host).await;
    let second = queued(&mut peer, &mut host).await;
    let mut bg = Background::new(peer, 3_600_000).await;
    bg.until(&mut host, |h| h.executions.len() == 1).await;
    let again = bg
        .api(
            "api/runs/control",
            Some(json!({"id":first["id"],"action":"resume"})),
            &mut host,
        )
        .await
        .unwrap();
    assert_eq!(again["run"]["queued_at"], first["queued_at"]);
    bg.api(
        "api/runs/control",
        Some(json!({"id":first["id"],"action":"pause"})),
        &mut host,
    )
    .await
    .unwrap();
    bg.until(&mut host, |h| saved(h, &first["id"])["inflight"].is_null())
        .await;
    let before = saved(&host, &first["id"])["attempts"]
        .as_array()
        .unwrap()
        .len();
    assert_eq!(saved(&host, &first["id"])["status"], "paused");
    let resumed = bg
        .api(
            "api/runs/control",
            Some(json!({"id":first["id"],"action":"resume"})),
            &mut host,
        )
        .await
        .unwrap();
    assert!(resumed["run"]["queued_at"].as_u64() > second["queued_at"].as_u64());
    bg.until(&mut host, |h| {
        saved(h, &second["id"])["status"] == "completed"
    })
    .await;
    assert_eq!(
        saved(&host, &first["id"])["attempts"]
            .as_array()
            .unwrap()
            .len(),
        before
    );
    bg.api(
        "api/runs/control",
        Some(json!({"id":first["id"],"action":"stop"})),
        &mut host,
    )
    .await
    .unwrap();
    bg.until(&mut host, |h| saved(h, &first["id"])["inflight"].is_null())
        .await;
    assert_eq!(saved(&host, &first["id"])["status"], "stopped");
    bg.cancel(&mut host).await;
}

#[tokio::test]
async fn error_pauses_only_its_run_and_continues_next() {
    let mut peer = Peer::new().await;
    let mut host = Host::default();
    let first = queued(&mut peer, &mut host).await;
    let second = queued(&mut peer, &mut host).await;
    host.fail = true;
    let mut bg = Background::new(peer, 3_600_000).await;
    bg.until(&mut host, |h| saved(h, &first["id"])["status"] == "paused")
        .await;
    assert_eq!(host.executions.len(), 1);
    assert!(
        saved(&host, &first["id"])["task_error"]
            .as_str()
            .unwrap()
            .contains("network")
    );
    assert!(
        !saved(&host, &first["id"])
            .to_string()
            .contains("fixture-secret")
    );
    host.fail = false;
    bg.until(&mut host, |h| {
        saved(h, &second["id"])["status"] == "completed"
    })
    .await;
    assert_eq!(host.executions.len(), 37);
    bg.cancel(&mut host).await;
}

#[tokio::test]
async fn account_change_pauses_before_sending() {
    let mut peer = Peer::new().await;
    let mut host = Host::default();
    let run = queued(&mut peer, &mut host).await;
    host.account_patch = Some(json!({"upstream_account_id":"replacement"}));
    let mut bg = Background::new(peer, 3_600_000).await;
    bg.until(&mut host, |h| saved(h, &run["id"])["status"] == "paused")
        .await;
    assert!(host.executions.is_empty());
    assert!(
        saved(&host, &run["id"])["task_error"]
            .as_str()
            .unwrap()
            .contains("身份已改变")
    );
    bg.cancel(&mut host).await;
}

#[tokio::test]
async fn restart_pauses_all_and_charges_unknown_once() {
    let mut peer = Peer::new().await;
    let mut host = Host::default();
    let first = queued(&mut peer, &mut host).await;
    let second = queued(&mut peer, &mut host).await;
    let mut bg = Background::new(peer, 3_600_000).await;
    bg.until(&mut host, |h| h.executions.len() == 1).await;
    drop(bg);
    host.model_open = false;
    host.model_events = None;
    let mut peer = Peer::new().await;
    peer.api("api/runs", None, &mut host).await.unwrap();
    for run in [&first, &second] {
        assert_eq!(saved(&host, &run["id"])["status"], "paused");
        assert!(saved(&host, &run["id"])["queued_at"].is_null());
    }
    assert_eq!(
        saved(&host, &first["id"])["attempts"][0]["error"],
        "interrupted_unknown_result"
    );
    assert_eq!(host.executions.len(), 1);
    let third = queued(&mut peer, &mut host).await;
    let mut bg = Background::new(peer, 3_600_000).await;
    bg.until(&mut host, |h| {
        saved(h, &third["id"])["status"] == "completed"
    })
    .await;
    assert_eq!(
        saved(&host, &first["id"])["attempts"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(host.executions.len(), 37);
    bg.cancel(&mut host).await;
}

#[tokio::test]
async fn persistence_failure_ends_parent_and_pauses_without_repeating() {
    let mut peer = Peer::new().await;
    let mut host = Host::default();
    let first = queued(&mut peer, &mut host).await;
    let second = queued(&mut peer, &mut host).await;
    host.reject_completed_write = true;
    let mut bg = Background::new(peer, 3_600_000).await;
    assert!(
        bg.finish(&mut host)
            .await
            .unwrap_err()
            .message
            .contains("state unavailable")
    );
    assert_eq!(host.executions.len(), 1);
    host.reject_completed_write = false;
    let mut bg = Background::new(bg.peer, 150_000).await;
    bg.finish(&mut host).await.unwrap();
    assert_eq!(saved(&host, &first["id"])["status"], "paused");
    assert_eq!(saved(&host, &second["id"])["status"], "paused");
    assert_eq!(host.executions.len(), 1);
}

#[tokio::test]
async fn handoff_requires_a_full_question_window() {
    let mut peer = Peer::new().await;
    let mut host = Host::default();
    let run = queued(&mut peer, &mut host).await;
    let mut bg = Background::new(peer, 150_000).await;
    bg.finish(&mut host).await.unwrap();
    assert_eq!(saved(&host, &run["id"])["status"], "ready");
    assert!(host.executions.is_empty());
    let mut bg = Background::new(bg.peer, 3_600_000).await;
    bg.until(&mut host, |h| saved(h, &run["id"])["status"] == "completed")
        .await;
    bg.cancel(&mut host).await;
}

#[tokio::test]
async fn preparation_and_scoring_errors_are_persisted_without_losing_samples() {
    for after_send in [false, true] {
        let mut peer = Peer::new().await;
        let mut host = Host::default();
        let run = queued(&mut peer, &mut host).await;
        let mut bg = Background::new(peer, 3_600_000).await;
        if after_send {
            bg.until(&mut host, |h| h.executions.len() == 1 && !h.model_open)
                .await;
        }
        host.state.values_mut().next().unwrap().0["plan"]["hash"] = json!("changed");
        bg.until(&mut host, |h| saved(h, &run["id"])["status"] == "paused")
            .await;
        let state = saved(&host, &run["id"]);
        assert!(state["inflight"].is_null());
        assert!(
            state["task_error"]
                .as_str()
                .unwrap()
                .contains("baseline_changed")
        );
        assert_eq!(host.executions.len(), usize::from(after_send));
        if after_send {
            assert_eq!(state["attempts"][0]["status"], "ok");
        }
        // Ending a task remains possible even when its scorer cannot load the plan.
        let stopped = bg
            .api(
                "api/runs/control",
                Some(json!({"id":run["id"],"action":"stop"})),
                &mut host,
            )
            .await
            .unwrap();
        assert_eq!(stopped["run"]["status"], "stopped");
        bg.cancel(&mut host).await;
    }
}

#[tokio::test]
async fn idle_maintenance_accepts_new_work_and_legacy_resume_can_opt_in() {
    let peer = Peer::new().await;
    let mut host = Host::default();
    let mut bg = Background::new(peer, 3_600_000).await;
    // Complete the initialization scan and let maintenance suspend waiting for work.
    bg.until(&mut host, |h| {
        h.callbacks
            .iter()
            .filter(|m| *m == "host.state.get")
            .count()
            >= 32
    })
    .await;
    let manual=bg.api("api/runs/start",Some(json!({"account_id":"account-b","key_id":"key-b","request_model":"gpt-6-astra","claimed_model":"gpt-6-astra","tier":"low"})),&mut host).await.unwrap()["run"].clone();
    assert_eq!(manual["background"], false);
    bg.api(
        "api/runs/control",
        Some(json!({"id":manual["id"],"action":"resume","background":true})),
        &mut host,
    )
    .await
    .unwrap();
    bg.until(&mut host, |h| {
        saved(h, &manual["id"])["status"] == "completed"
    })
    .await;
    assert_eq!(host.executions.len(), 36);
    bg.cancel(&mut host).await;
}

#[tokio::test]
async fn cancelled_maintenance_recovers_pending_in_same_process_without_resending() {
    let mut peer = Peer::new().await;
    let mut host = Host::default();
    let run = queued(&mut peer, &mut host).await;
    let mut bg = Background::new(peer, 3_600_000).await;
    bg.until(&mut host, |h| h.executions.len() == 1).await;
    let peer = bg.cancel(&mut host).await;
    let mut bg = Background::new(peer, 3_600_000).await;
    bg.until(&mut host, |h| saved(h, &run["id"])["status"] == "paused")
        .await;
    assert_eq!(host.executions.len(), 1);
    assert_eq!(
        saved(&host, &run["id"])["attempts"][0]["error"],
        "interrupted_unknown_result"
    );
    bg.cancel(&mut host).await;
}
