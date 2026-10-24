use crate::{
    domain::{AccountIdentity, Run},
    invalid,
};
use gateway_plugin_sdk::{ErrorCode, PluginFault, SendState, call::host::*, client::HostClient};
use serde::{Serialize, de::DeserializeOwned};
use serde_json::{Value, json};
use std::collections::BTreeSet;

mod responses;
use responses::ResponsesStream;

pub async fn metadata<I: Serialize, O: DeserializeOwned>(
    host: &HostClient,
    method: &str,
    input: I,
) -> Result<O, PluginFault> {
    let reply = host
        .call(
            method,
            serde_json::to_value(input).map_err(|_| invalid("回调编码失败"))?,
            vec![],
        )
        .await
        .map_err(|e| e.into_plugin_fault())?;
    if !reply.payload.is_empty() {
        return Err(invalid("宿主元数据回调夹带了正文"));
    }
    serde_json::from_value(reply.result).map_err(|_| invalid("宿主回调响应格式错误"))
}
async fn payload<I: Serialize, O: DeserializeOwned>(
    host: &HostClient,
    method: &str,
    input: I,
) -> Result<O, PluginFault> {
    let reply = host
        .call(
            method,
            json!({}),
            serde_json::to_vec(&input).map_err(|_| invalid("回调编码失败"))?,
        )
        .await
        .map_err(|e| e.into_plugin_fault())?;
    serde_json::from_slice(&reply.payload).map_err(|_| invalid("宿主账号回调响应格式错误"))
}

pub async fn accounts(host: &HostClient) -> Result<Vec<AuthRuntimeAccount>, PluginFault> {
    let mut cursor = None;
    let mut seen = BTreeSet::new();
    let mut accounts = vec![];
    loop {
        let page: AuthListResult = payload(
            host,
            "host.auth.list",
            AuthListRequest {
                provider_id: Some("openai".into()),
                cursor,
                limit: 100,
            },
        )
        .await?;
        accounts.extend(
            page.accounts
                .into_iter()
                .filter(|a| a.enabled && a.provider_id == "openai"),
        );
        cursor = page.next_cursor;
        let Some(next) = &cursor else {
            return Ok(accounts);
        };
        if !seen.insert(next.clone()) || seen.len() > 100 {
            return Err(invalid("账号分页重复或超过 100 页"));
        }
    }
}
pub async fn keys(host: &HostClient) -> Result<Vec<ClientKey>, PluginFault> {
    let mut cursor = None;
    let mut seen = BTreeSet::new();
    let mut keys = vec![];
    loop {
        let page = host
            .list_keys(KeyListRequest { cursor, limit: 100 })
            .await?;
        keys.extend(page.keys.into_iter().filter(|k| k.enabled));
        cursor = page.next_cursor;
        let Some(next) = &cursor else {
            return Ok(keys);
        };
        if !seen.insert(next.clone()) || seen.len() > 100 {
            return Err(invalid("Key 分页重复或超过 100 页"));
        }
    }
}
pub async fn models(host: &HostClient, key: &str) -> Result<ModelListResult, PluginFault> {
    metadata(
        host,
        "host.models.list",
        ModelListRequest {
            client_key_id: key.into(),
            protocol: "openai".into(),
            client_version: concat!("model-health/", env!("CARGO_PKG_VERSION")).into(),
        },
    )
    .await
}
pub fn account_identity(account: &AuthRuntimeAccount) -> AccountIdentity {
    AccountIdentity {
        authentication_kind: account.authentication_kind.clone(),
        upstream_user_id: account.upstream_user_id.clone(),
        upstream_account_id: account.upstream_account_id.clone(),
    }
}

pub async fn validate_account(host: &HostClient, run: &mut Run) -> Result<(), PluginFault> {
    let account: AuthRuntimeAccount = payload(
        host,
        "host.auth.get_runtime",
        AuthGetRequest {
            account_id: run.account_id.clone(),
        },
    )
    .await?;
    if !account.enabled || account.provider_id != "openai" || account.account_id != run.account_id {
        return Err(invalid(
            "检测账号已停用或所属账号/平台发生变化，请检查账号状态",
        ));
    }
    let identity = account_identity(&account);
    let revision_changed = account.credential_revision != run.credential_revision;
    match &run.account_identity {
        Some(expected) if expected != &identity => {
            return Err(invalid(
                "账号身份已改变，请结束当前检测后新建，避免混合不同账号的样本",
            ));
        }
        None if revision_changed && !run.attempts.is_empty() => {
            // 旧记录没有上游身份快照，不能用当前身份反填已完成样本的归属。
            return Err(invalid(
                "这条旧检测缺少账号身份快照且凭据已更新，请结束后新建检测；历史结果保留",
            ));
        }
        _ => {}
    }
    let has_identity = [
        identity.upstream_user_id.as_deref(),
        identity.upstream_account_id.as_deref(),
    ]
    .into_iter()
    .flatten()
    .any(|id| !id.is_empty());
    if revision_changed && !has_identity && !run.attempts.is_empty() {
        return Err(invalid(
            "该账号缺少稳定的上游身份且凭据已更新，请结束后新建检测",
        ));
    }
    // Cookie 回写、刷新退避和令牌轮换都会推进 revision；它不是账号身份版本。
    // 随同 pending/续测状态一起保存本次检查值，不冒充实际发送后的凭据版本。
    run.account_identity = Some(identity);
    run.credential_revision = account.credential_revision;
    Ok(())
}
pub async fn read(host: &HostClient, slot: usize) -> Result<Option<(Run, u64)>, PluginFault> {
    let reply: StateGetResult = metadata(
        host,
        "host.state.get",
        StateGetRequest {
            namespace: "runs".into(),
            key: format!("run-{slot}"),
        },
    )
    .await?;
    reply
        .record
        .map(|r| {
            serde_json::from_value(r.value)
                .map(|run| (run, r.version))
                .map_err(|_| invalid("检测状态格式错误"))
        })
        .transpose()
}
pub async fn write(host: &HostClient, run: &Run, version: Option<u64>) -> Result<(), PluginFault> {
    let _: StatePutResult = metadata(
        host,
        "host.state.put",
        StatePutRequest {
            namespace: "runs".into(),
            key: format!("run-{}", run.slot),
            value: serde_json::to_value(run).map_err(|_| invalid("状态编码失败"))?,
            expected_version: version,
        },
    )
    .await?;
    Ok(())
}

pub struct ExecutionFailure {
    pub request_id: Option<String>,
    pub fault: PluginFault,
}
impl From<PluginFault> for ExecutionFailure {
    fn from(fault: PluginFault) -> Self {
        Self {
            request_id: None,
            fault,
        }
    }
}

pub async fn execute(
    host: &HostClient,
    run: &Run,
    body: Value,
) -> Result<(String, String), ExecutionFailure> {
    let request = ModelExecuteRequest {
        client_key_id: Some(run.key_id.clone()),
        model: run.plan["request_model"]
            .as_str()
            .ok_or_else(|| invalid("缺少模型"))?
            .into(),
        protocol: "openai".into(),
        operation: ModelOperation::Generate,
        provider: Some("openai".into()),
        account_id: Some(run.account_id.clone()),
        previous_response_id: None,
    };
    let reply = host
        .call(
            "host.model.execute_stream",
            serde_json::to_value(request).map_err(|_| invalid("模型元数据编码失败"))?,
            serde_json::to_vec(&body).map_err(|_| invalid("模型正文编码失败"))?,
        )
        .await
        .map_err(|e| e.into_plugin_fault())?;
    let result: ModelStreamResult =
        serde_json::from_value(reply.result).map_err(|_| invalid("模型响应缺少请求 ID"))?;
    let mut ended = false;
    let read = tokio::time::timeout(
        std::time::Duration::from_secs(90),
        read_stream(host, &result.stream, &mut ended),
    )
    .await;
    match read {
        Ok(Ok(sse)) => Ok((result.request_id, sse)),
        other => {
            let mut fault = match other {
                Ok(Err(error)) => error,
                _ => stream_fault(ErrorCode::Timeout, "模型流读取达到 90 秒上限"),
            };
            // end=true 时宿主已回收句柄；不能再次关闭并用权限错误覆盖真正原因。
            if !ended
                && let Err(error) = host
                    .call(
                        "host.model.stream_close",
                        json!({"stream":result.stream}),
                        vec![],
                    )
                    .await
            {
                fault.message.push_str(&format!(
                    "；关闭执行流：{}",
                    error.into_plugin_fault().message
                ));
            }
            Err(ExecutionFailure {
                request_id: Some(result.request_id),
                fault,
            })
        }
    }
}

fn stream_fault(code: ErrorCode, message: &str) -> PluginFault {
    // 已进入模型执行流程；本地解码失败不代表上游未发送，不能沿用默认 NotSent。
    let mut fault = PluginFault::new(code, message);
    fault.send_state = SendState::Ambiguous;
    fault
}

async fn read_stream(
    host: &HostClient,
    stream: &str,
    ended: &mut bool,
) -> Result<String, PluginFault> {
    let mut response = ResponsesStream::default();
    loop {
        let reply = host
            .call(
                "host.model.stream_read",
                json!({"stream":stream,"maximum_bytes":262144}),
                vec![],
            )
            .await
            .map_err(|e| e.into_plugin_fault())?;
        let state: ModelStreamReadResult = serde_json::from_value(reply.result)
            .map_err(|_| stream_fault(ErrorCode::Fault, "模型流状态格式错误"))?;
        *ended = state.end;
        let batch = if reply.payload.is_empty() && state.events == 0 {
            ModelEventBatch::default()
        } else {
            ModelEventBatch::decode(&reply.payload)
                .map_err(|_| stream_fault(ErrorCode::Fault, "模型事件批次格式错误"))?
        };
        if batch.events.len() != state.events as usize {
            return Err(stream_fault(ErrorCode::Fault, "模型事件数量不一致"));
        }
        for event in batch.events {
            response.push(event)?;
        }
        // response.completed 不是句柄 EOF；继续读到宿主结算完成才交给评分器。
        if state.end {
            return Ok(response.finish());
        }
    }
}
