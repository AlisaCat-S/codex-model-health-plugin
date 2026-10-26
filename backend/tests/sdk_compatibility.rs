//! SDK 升级同时核对线协议、能力版本和宿主范围，不能只凭能编译判断兼容。
use gateway_plugin_sdk::call::model::{ExecutionEvent, facts::ResponseObservation};
use gateway_plugin_sdk::{Capability, Manifest, PROTOCOL_VERSION, ResolvedCallBudgets, Stage};
use serde_json::{Value, json};

#[test]
fn management_contract_is_unchanged_but_legacy_hosts_are_outside_the_manifest_range() {
    let manifest = Manifest::from_author_slice(include_bytes!("../../plugin.json")).unwrap();
    assert_eq!(PROTOCOL_VERSION, 7);
    assert_eq!(manifest.plugin_id().unwrap(), "local.model-health");
    assert_eq!(manifest.contributes.len(), 2);
    assert_eq!(manifest.contributes[&Capability::Maintenance].version, 1);
    let management = &manifest.contributes[&Capability::Management];
    assert_eq!(management.version, 2);
    assert_eq!(management.stages, [Stage::Management]);
    let range = &manifest.engines.codex_proxy_rs;
    assert!(range.matches(&"3.33.0".parse().unwrap()));
    for version in [
        "3.29.7", "3.30.2", "3.31.0", "3.31.1", "3.31.3", "3.32.0", "4.0.0",
    ] {
        assert!(!range.matches(&version.parse().unwrap()), "{version}");
    }
    assert_eq!(manifest.state.len(), 1);
    assert_eq!(manifest.state[0].namespace, "runs");
    assert_eq!(manifest.state[0].schema_version, 1);
    assert_eq!(
        ResolvedCallBudgets::resolve(&Default::default())
            .unwrap()
            .budget(Stage::Management),
        std::time::Duration::from_secs(120)
    );
}

#[test]
fn release_versions_and_host_notes_match_the_migration_target() {
    let manifest: Value = serde_json::from_slice(include_bytes!("../../plugin.json")).unwrap();
    let frontend: Value =
        serde_json::from_slice(include_bytes!("../../frontend/package.json")).unwrap();
    let base = manifest["version"]
        .as_str()
        .unwrap()
        .split('-')
        .next()
        .unwrap();
    assert_eq!(base, "0.3.0");
    assert_eq!(manifest["version"], env!("CARGO_PKG_VERSION"));
    assert_eq!(frontend["version"], base);
    let workflow = include_str!("../../.github/workflows/release.yml");
    assert!(workflow.contains("对应宿主：[Codex Proxy RS v3.33.0]"));
    assert!(workflow.contains(&format!("RPC **v{PROTOCOL_VERSION}**")));
    assert!(workflow.contains("${HOST_RANGE}"));
    assert!(workflow.contains("docs/sdk-upgrade-2026-10-26.md"));
}

#[tokio::test]
async fn rpc_v5_and_v6_handshakes_are_rejected_instead_of_downgraded() {
    use gateway_plugin_sdk::{
        Frame, Handshake, Message,
        client::{PluginSession, SessionConfig, SessionError, write_frame},
    };
    for protocol_version in [5, 6] {
        let (mut host, plugin) = tokio::io::duplex(4096);
        let manifest = Manifest::from_author_slice(include_bytes!("../../plugin.json")).unwrap();
        write_frame(
            &mut host,
            &Frame::control(Message::Hello {
                handshake: Handshake {
                    protocol_version,
                    artifact_sha256: "a".repeat(64),
                    plugin_id: "local.model-health".into(),
                    instance_id: "test".into(),
                    generation: 1,
                    incarnation: "test".into(),
                    configuration: json!({}),
                    contributes: manifest.contributes,
                },
            }),
        )
        .await
        .unwrap();
        let (reader, writer) = tokio::io::split(plugin);
        assert!(matches!(
            PluginSession::accept(reader, writer, SessionConfig::default()).await,
            Err(SessionError::Handshake)
        ));
    }
}

#[test]
fn sdk_cli_and_lockfile_use_the_same_fixed_host_revision() {
    let cargo = include_str!("../Cargo.toml");
    let revision = cargo
        .split("rev = \"")
        .nth(1)
        .unwrap()
        .split('"')
        .next()
        .unwrap();
    assert_eq!(revision.len(), 40);
    assert!(revision.bytes().all(|byte| byte.is_ascii_hexdigit()));
    assert!(
        include_str!("../../.github/workflows/release.yml").contains(&format!("--rev {revision}"))
    );
    assert!(include_str!("../Cargo.lock").contains(&format!("?rev={revision}#{revision}")));
}

#[test]
fn removed_observation_field_is_incompatible_even_when_null() {
    let observation = serde_json::to_value(ResponseObservation::new("websocket")).unwrap();
    assert!(observation.get("upstream_response_model").is_none());
    // 3.30.2 的宿主会序列化此字段（含 null）。v3.31.1 的 deny_unknown_fields
    // 会拒绝整个 GPE2 事件，尽管两者都声明 RPC v5。
    for old_model in [Value::Null, json!("legacy-model")] {
        let mut legacy = observation.clone();
        legacy["upstream_response_model"] = old_model;
        assert!(serde_json::from_value::<ResponseObservation>(legacy.clone()).is_err());
        let metadata = serde_json::to_vec(&json!({
            "host": {"observation":legacy,"middleware_transformed":false}
        }))
        .unwrap();
        let mut bytes = b"GPE2".to_vec();
        bytes.extend_from_slice(&(metadata.len() as u32).to_be_bytes());
        bytes.extend_from_slice(&[0; 8]);
        bytes.extend_from_slice(&metadata);
        assert!(ExecutionEvent::decode(&bytes).is_err());
    }
}
