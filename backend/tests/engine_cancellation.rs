use codex_model_health_plugin::engine::Engine;
use serde_json::json;
use std::{ffi::OsString, time::Duration};

fn engine(script: &str) -> Engine {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap();
    let command: Vec<OsString> = if let Some(python) = std::env::var_os("MODEL_HEALTH_TEST_PYTHON")
    {
        vec![
            python,
            "-X".into(),
            "utf8".into(),
            "-B".into(),
            "-u".into(),
            "-c".into(),
            script.into(),
            root.join("engine").into_os_string(),
        ]
    } else {
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "-v",
            &format!("{}:/fixture:ro", root.display()),
            "--entrypoint",
            "python",
            "meow-llm-detector:4.5.4",
            "-u",
            "-c",
            script,
            "/fixture/engine",
        ]
        .into_iter()
        .map(Into::into)
        .collect()
    };
    Engine::command(command)
}

#[tokio::test]
async fn cancelled_exchange_cannot_feed_its_late_reply_into_the_next_query() {
    let engine = engine(
        "import sys,json,time\nfor line in sys.stdin:\n d=json.loads(line);time.sleep(d['delay']);print(json.dumps({'ok':True,'data':d['value']}),flush=True)",
    );
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

#[tokio::test]
async fn cancelled_catalog_cannot_be_saved_as_the_next_run_plan() {
    let engine = engine(
        "import sys,json,time;sys.path.insert(0,sys.argv[1]);import worker\nfor i,line in enumerate(sys.stdin):\n if i==0:time.sleep(1)\n print(json.dumps({'ok':True,'data':worker.handle(json.loads(line))}),flush=True)",
    );
    assert!(
        tokio::time::timeout(
            Duration::from_millis(100),
            engine.query(json!({"op":"catalog"}))
        )
        .await
        .is_err()
    );
    let plan = engine.query(json!({"op":"prepare","method":"meow","tier":"low","claimed_model":"gpt-6-astra","request_model":"gpt-6-astra"})).await.unwrap();
    assert_eq!(plan["request_model"], "gpt-6-astra");
    assert_eq!(plan["jobs"].as_array().unwrap().len(), 36);
    let report = engine
        .query(json!({"op":"score","plan":plan,"results":[]}))
        .await
        .unwrap();
    assert_eq!(report["verdict"], "insufficient");
    let payload = engine
        .query(json!({"op":"payload","plan":plan,"job_id":plan["jobs"][0]["job_id"]}))
        .await
        .unwrap();
    assert_eq!(payload["model"], "gpt-6-astra");
}
