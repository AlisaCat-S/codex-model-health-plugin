use codex_model_health_plugin::engine::Engine;
use serde_json::json;
use std::{ffi::OsString, time::Duration};

#[tokio::test]
async fn cancelled_exchange_cannot_feed_its_late_reply_into_the_next_query() {
    let script = "import sys,json,time\nfor line in sys.stdin:\n d=json.loads(line);time.sleep(d['delay']);print(json.dumps({'ok':True,'data':d['value']}),flush=True)";
    let command: Vec<OsString> = if let Some(python) = std::env::var_os("MODEL_HEALTH_TEST_PYTHON")
    {
        vec![python, "-u".into(), "-c".into(), script.into()]
    } else {
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--entrypoint",
            "python",
            "meow-llm-detector:4.5.4",
            "-u",
            "-c",
            script,
        ]
        .into_iter()
        .map(Into::into)
        .collect()
    };
    let engine = Engine::command(command);
    assert!(
        tokio::time::timeout(
            Duration::from_millis(100),
            engine.query(json!({"delay":1,"value":"cancelled"}))
        )
        .await
        .is_err()
    );
    assert_eq!(
        engine
            .query(json!({"delay":0,"value":"next"}))
            .await
            .unwrap(),
        "next"
    );
}
