//! SDK 升级同时核对线协议、能力版本和宿主范围，不能只凭能编译判断兼容。
use gateway_plugin_sdk::call::model::{ExecutionEvent, facts::ResponseObservation};
use gateway_plugin_sdk::{Capability, Manifest, PROTOCOL_VERSION, Stage};
use serde_json::{Value, json};

#[test]
fn management_contract_is_unchanged_but_legacy_hosts_are_outside_the_manifest_range() {
    let manifest = Manifest::from_author_slice(include_bytes!("../../plugin.json")).unwrap();
    assert_eq!(PROTOCOL_VERSION, 5);
    assert_eq!(manifest.plugin_id().unwrap(), "local.model-health");
    assert_eq!(manifest.contributes.len(), 1);
    let management = &manifest.contributes[&Capability::Management];
    assert_eq!(management.version, 2);
    assert_eq!(management.stages, [Stage::Management]);
    let range = &manifest.engines.codex_proxy_rs;
    assert!(range.matches(&"3.31.1".parse().unwrap()));
    for version in ["3.29.7", "3.30.2", "3.31.0", "4.0.0"] {
        assert!(!range.matches(&version.parse().unwrap()), "{version}");
    }
    assert_eq!(manifest.state.len(), 1);
    assert_eq!(manifest.state[0].namespace, "runs");
    assert_eq!(manifest.state[0].schema_version, 1);
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
