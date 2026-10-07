#[cfg(feature = "bundled-engine")]
#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    use gateway_plugin_sdk::client::{PluginSession, SessionConfig};
    let session = PluginSession::accept(
        tokio::io::stdin(),
        tokio::io::stdout(),
        SessionConfig::default(),
    )
    .await?;
    if session.handshake().plugin_id != "local.model-health" {
        return Err("插件身份不匹配".into());
    }
    session
        .run(codex_model_health_plugin::plugin(
            codex_model_health_plugin::engine::Engine::bundled()?,
        )?)
        .await?;
    Ok(())
}
#[cfg(not(feature = "bundled-engine"))]
fn main() {
    eprintln!(
        "发布构建需要 bundled-engine 特性与 MEOW_ENGINE_BINARY；测试使用显式 Engine::command"
    );
    std::process::exit(64);
}
