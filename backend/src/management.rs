use crate::{
    Service,
    domain::{Method, Run, SLOTS, Status, slot_from_id},
    host, invalid, now_ms, now_nanos, runner, updates,
};
use gateway_plugin_sdk::{
    ErrorCode, PluginFault,
    call::management::*,
    client::{HostClient, TypedCall, TypedReply},
};
use serde::Deserialize;
use serde_json::{Value, json};

pub fn registration() -> ManagementRegistration {
    ManagementRegistration {
        routes: [
            ("GET", "api/bootstrap"),
            ("POST", "api/upstreams/check"),
            ("POST", "api/models"),
            ("GET", "api/runs"),
            ("POST", "api/runs/get"),
            ("POST", "api/runs/start"),
            ("POST", "api/runs/step"),
            ("POST", "api/runs/control"),
        ]
        .into_iter()
        .map(|(method, path)| ManagementRoute {
            method: method.into(),
            path: path.into(),
            request_content_types: if method == "POST" {
                vec!["application/json".into()]
            } else {
                vec![]
            },
            response_content_types: vec!["application/json".into()],
        })
        .collect(),
        resources: ["web/index.html", "web/app.js", "web/app.css"]
            .into_iter()
            .map(|path| ManagementResource {
                path: path.into(),
                public: false,
            })
            .collect(),
        pages: vec![ManagementPage {
            id: "model-health".into(),
            title: "账号模型体检".into(),
            description: Some("选择已有账号，使用 Meow 或 ModelTrace 检测模型行为指纹".into()),
            entry: "web/index.html".into(),
            icon: None,
        }],
        callbacks: vec![],
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Start {
    #[serde(default)]
    background: bool,
    #[serde(default)]
    method: Method,
    account_id: String,
    key_id: String,
    request_model: String,
    claimed_model: String,
    tier: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Identity {
    id: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Control {
    id: String,
    action: String,
    #[serde(default)]
    background: Option<bool>,
}

fn input<T: serde::de::DeserializeOwned>(
    call: &TypedCall<ManagementRequest>,
) -> Result<T, PluginFault> {
    serde_json::from_slice(&call.payload).map_err(|_| invalid("请求参数格式错误"))
}
fn reply(value: Value) -> Result<TypedReply<ManagementResponse>, PluginFault> {
    reply_status(200, value)
}
fn reply_status(status: u16, value: Value) -> Result<TypedReply<ManagementResponse>, PluginFault> {
    Ok(TypedReply::new(ManagementResponse {
        status,
        content_type: "application/json".into(),
        headers: vec![],
    })
    .with_payload(serde_json::to_vec(&value).map_err(|_| invalid("响应编码失败"))?))
}
pub(crate) async fn find(host: &HostClient, id: &str) -> Result<(Run, u64), PluginFault> {
    let (run, version) = host::read(host, slot_from_id(id)?)
        .await?
        .ok_or_else(|| invalid("检测记录不存在"))?;
    if run.id != id {
        return Err(invalid("检测记录已超出 16 条历史保留窗口"));
    }
    Ok((run, version))
}
pub(crate) async fn histories(host: &HostClient) -> Result<Vec<(Run, u64)>, PluginFault> {
    let mut runs = Vec::new();
    for slot in 0..SLOTS {
        if let Some(run) = host::read(host, slot).await? {
            runs.push(run);
        }
    }
    runs.sort_by_key(|(r, _)| std::cmp::Reverse(r.created_at));
    Ok(runs)
}
pub(crate) async fn update_report(service: &Service, run: &mut Run) -> Result<(), PluginFault> {
    run.report = service
        .engine
        .query(json!({"op":"score","plan":run.plan,"results":run.attempts}))
        .await?;
    run.updated_at = now_ms();
    Ok(())
}

pub async fn handle(
    service: &Service,
    call: TypedCall<ManagementRequest>,
) -> Result<TypedReply<ManagementResponse>, PluginFault> {
    match dispatch(service, call).await {
        Ok(response) => Ok(response),
        Err(error) => {
            let status = match error.code {
                ErrorCode::InvalidInput => 400,
                ErrorCode::Rejected | ErrorCode::PermissionDenied => 403,
                ErrorCode::Unsupported => 404,
                ErrorCode::Conflict => 409,
                ErrorCode::Capacity => 503,
                ErrorCode::Timeout => 504,
                ErrorCode::Upstream => 502,
                ErrorCode::Fault | ErrorCode::Cancelled | ErrorCode::Uncertain => 500,
            };
            // 应用错误走 HTTP 响应；协议 Error 会被宿主替换成泛化的“副作用”提示。
            // 不转发原始 details；保留有界原因和发送事实，页面不会自动重试。
            reply_status(
                status,
                json!({"error": {
                    "code": error.code,
                    "message": error.message.chars().take(512).collect::<String>(),
                    "send_state": error.send_state,
                }}),
            )
        }
    }
}

async fn dispatch(
    service: &Service,
    call: TypedCall<ManagementRequest>,
) -> Result<TypedReply<ManagementResponse>, PluginFault> {
    if !call.request.query.is_empty() || call.payload.len() > 8192 {
        return Err(invalid("管理请求大小或查询参数不符合接口"));
    }
    if call.request.path.starts_with("api/runs") {
        runner::initialize(service, &call.host).await?;
    }
    match (call.request.method.as_str(), call.request.path.as_str()) {
        ("GET", "api/bootstrap") => {
            let catalog = service.engine.query(json!({"op":"catalog"})).await?;
            let accounts = host::accounts(&call.host)
                .await?
                .into_iter()
                .map(|a| {
                    json!({"id":a.account_id,"name":a.name,"email":a.email,"provider":a.provider_id,"plan":a.plan_type})
                })
                .collect::<Vec<_>>();
            reply(
                json!({"catalog":catalog,"sources":updates::sources()?,"accounts":accounts,"keys":host::keys(&call.host).await?}),
            )
        }
        ("POST", "api/upstreams/check") => {
            #[derive(Deserialize)]
            #[serde(deny_unknown_fields)]
            struct Check {
                method: Method,
            }
            let query: Check = input(&call)?;
            reply(json!({"check":service.updates.check(&call.host, query.method).await?}))
        }
        ("POST", "api/models") => {
            #[derive(Deserialize)]
            #[serde(deny_unknown_fields)]
            struct ModelInput {
                key_id: String,
            }
            let query: ModelInput = input(&call)?;
            reply(
                serde_json::to_value(host::models(&call.host, &query.key_id).await?)
                    .map_err(|_| invalid("模型列表编码失败"))?,
            )
        }
        ("GET", "api/runs") => reply(
            json!({"runs":histories(&call.host).await?.iter().map(|(r,_)|r.summary()).collect::<Vec<_>>()}),
        ),
        ("POST", "api/runs/get") => {
            let query: Identity = input(&call)?;
            let (run, _) = find(&call.host, &query.id).await?;
            reply(json!({"run":run.detail(),"busy":service.execution.available_permits()==0}))
        }
        ("POST", "api/runs/start") => start(service, &call.host, input(&call)?).await,
        ("POST", "api/runs/control") => control(service, &call.host, input(&call)?).await,
        ("POST", "api/runs/step") => {
            let query: Identity = input(&call)?;
            step(service, &call.host, &query.id).await
        }
        _ => Err(PluginFault::new(
            ErrorCode::Unsupported,
            "未注册的插件管理接口",
        )),
    }
}

async fn start(
    service: &Service,
    host: &HostClient,
    query: Start,
) -> Result<TypedReply<ManagementResponse>, PluginFault> {
    let account = host::accounts(host)
        .await?
        .into_iter()
        .find(|a| a.account_id == query.account_id)
        .ok_or_else(|| invalid("请选择已启用的 OpenAI 账号"))?;
    let key = host::keys(host)
        .await?
        .into_iter()
        .find(|k| k.id == query.key_id)
        .ok_or_else(|| invalid("请选择已启用的测试 Key"))?;
    if !host::models(host, &query.key_id)
        .await?
        .models
        .contains(&query.request_model)
    {
        return Err(invalid("当前 Key 的模型列表不包含所选模型"));
    }
    let plan=service.engine.query(json!({"op":"prepare","method":query.method,"tier":query.tier,"claimed_model":query.claimed_model,"request_model":query.request_model})).await?;
    let _lock = service.state.lock().await;
    let history = histories(host).await?;
    let slot = (0..SLOTS)
        .find(|s| !history.iter().any(|(r, _)| r.slot == *s))
        .or_else(|| {
            history
                .iter()
                .rev()
                .find(|(r, _)| r.finished())
                .map(|(r, _)| r.slot)
        })
        .ok_or_else(|| invalid("已有 16 个未结束任务，请先结束一个任务"))?;
    let version = history
        .iter()
        .find(|(r, _)| r.slot == slot)
        .map(|(_, v)| *v);
    let account_identity = host::account_identity(&account);
    let mut run = Run {
        id: format!("{slot}-{}", now_nanos()),
        slot,
        created_at: now_ms(),
        updated_at: now_ms(),
        account_id: account.account_id,
        account_name: account_name_for_display(account.email.as_deref(), &account.name),
        credential_revision: account.credential_revision,
        account_identity: Some(account_identity),
        key_id: key.id,
        key_name: key.name,
        plan,
        status: Status::Ready,
        attempts: vec![],
        inflight: None,
        report: Value::Null,
        background: query.background,
        queued_at: query.background.then(|| runner::queue_time(&history)),
        task_error: None,
    };
    update_report(service, &mut run).await?;
    if run.data_error().is_some() {
        return Err(invalid(
            "检测引擎返回的计划或报告不完整，未创建任务；请重新读取状态后重试",
        ));
    }
    host::write(host, &run, version).await?;
    service.wake.notify_one();
    reply(json!({"run":run.detail()}))
}

async fn control(
    service: &Service,
    host: &HostClient,
    query: Control,
) -> Result<TypedReply<ManagementResponse>, PluginFault> {
    if !["pause", "resume", "stop"].contains(&query.action.as_str()) {
        return Err(invalid("未知的任务控制操作"));
    }
    let _lock = service.state.lock().await;
    let (mut run, version) = find(host, &query.id).await?;
    if run.finished() {
        return Err(invalid("任务已结束，历史报告保持不变"));
    }
    if query.action == "resume"
        && let Some(error) = run.data_error()
    {
        return Err(invalid(error));
    }
    if query.action == "resume"
        && run.inflight.is_some()
        && service.execution.available_permits() == 0
    {
        // Repeated resume is harmless, but cannot undo a requested pause/stop.
        if run.background && run.queued_at.is_some() && run.status == Status::Running {
            return reply(json!({"run":run.detail()}));
        }
        return Err(invalid("当前题目尚在完成，请稍后刷新"));
    }
    match query.action.as_str() {
        "pause" => {
            run.status = Status::Paused;
            run.queued_at = None;
        }
        "stop" => {
            run.status = Status::Stopped;
            run.queued_at = None;
            if service.execution.available_permits() > 0 && run.inflight.is_some() {
                run.recover()?;
                run.status = Status::Stopped;
            }
        }
        "resume" => {
            if let Err(error) = host::validate_account(host, &mut run).await {
                if run.background || query.background == Some(true) {
                    runner::pause(&mut run, &error.message);
                    host::write(host, &run, Some(version)).await?;
                    return reply(json!({"run":run.detail()}));
                }
                return Err(error);
            }
            if run.background && run.queued_at.is_some() && run.status == Status::Ready {
                return reply(json!({"run":run.detail()}));
            }
            run.recover()?;
            run.background = query.background.unwrap_or(run.background);
            run.task_error = None;
            if run.background && run.status == Status::Ready {
                run.queued_at = Some(runner::queue_time(&histories(host).await?));
            }
        }
        _ => unreachable!(),
    }
    if query.action == "resume" {
        if let Err(error) = update_report(service, &mut run).await {
            if !run.background {
                return Err(error);
            }
            runner::pause(&mut run, &error.message);
        }
    } else {
        // Pausing/stopping must not depend on a healthy scoring subprocess.
        run.updated_at = now_ms();
    }
    host::write(host, &run, Some(version)).await?;
    service.wake.notify_one();
    reply(json!({"run":run.detail()}))
}

async fn step(
    service: &Service,
    host: &HostClient,
    id: &str,
) -> Result<TypedReply<ManagementResponse>, PluginFault> {
    let _execution = service
        .execution
        .try_acquire()
        .map_err(|_| invalid("另一个检测请求正在执行，请等待该题完成"))?;
    let run = advance(service, host, id, false).await?;
    reply(json!({"run":run.detail()}))
}

/// Caller owns the global execution permit. Never constructs an upstream HTTP client.
pub(crate) async fn advance(
    service: &Service,
    host: &HostClient,
    id: &str,
    background: bool,
) -> Result<Run, PluginFault> {
    let (snapshot, job, body) = {
        let _lock = service.state.lock().await;
        let (mut run, version) = find(host, id).await?;
        if run.background != background {
            return Err(invalid("后台托管任务不能手动逐题执行"));
        }
        if background && (run.status != Status::Ready || run.queued_at.is_none()) {
            return Ok(run); // pause/stop won the race with queue selection
        }
        if let Some(error) = run.data_error() {
            if !background {
                return Err(invalid(error));
            }
            runner::pause(&mut run, error);
            host::write(host, &run, Some(version)).await?;
            return Ok(run);
        }
        let job = run.next_job().ok_or_else(|| invalid("检测计划已完成"))?;
        let prepared = async {
            host::validate_account(host, &mut run).await?;
            service
                .engine
                .query(json!({"op":"payload","plan":run.plan,"job_id":job}))
                .await
        }
        .await;
        let body = match prepared {
            Ok(body) => body,
            Err(error) if background => {
                runner::pause(&mut run, &error.message);
                host::write(host, &run, Some(version)).await?;
                return Ok(run);
            }
            Err(error) => return Err(error),
        };
        run.reserve(&job)?;
        run.updated_at = now_ms();
        // 发送前写入 pending；未知结果不能恢复成免费重试。
        host::write(host, &run, Some(version)).await?;
        (run, job, body)
    };
    let result = match host::execute(host, &snapshot, body).await {
        Ok((request_id, sse)) => match service
            .engine
            .query(json!({"op":"evaluate","plan":snapshot.plan,"job_id":job,"sse":sse}))
            .await
        {
            Ok(mut sample) => {
                sample["request_id"] = json!(request_id);
                sample
            }
            Err(error) => {
                json!({"status":"error","error":excerpt(&error.message),"request_id":request_id})
            }
        },
        Err(error) => {
            // 只保存公开错误事实；fault.details 可能含原始上游正文或头，不能写入历史。
            json!({"status":"error","error":excerpt(&error.fault.message),"request_id":error.request_id,
                "error_code":error.fault.code,"http_status":error.fault.http_status,"send_state":error.fault.send_state})
        }
    };
    let _lock = service.state.lock().await;
    let (mut latest, version) = find(host, id).await?;
    latest.finish_attempt(result)?;
    if background
        && latest
            .attempts
            .last()
            .is_some_and(|a| a["status"] == "error")
    {
        let message = latest
            .attempts
            .last()
            .and_then(|a| a["error"].as_str())
            .unwrap_or("检测请求失败")
            .to_owned();
        runner::pause(&mut latest, &message);
    }
    let scored = update_report(service, &mut latest).await;
    if let Err(error) = &scored {
        runner::pause(&mut latest, &error.message);
    }
    host::write(host, &latest, Some(version)).await?;
    if !background {
        scored?;
    }
    Ok(latest)
}

pub(crate) fn excerpt(message: &str) -> String {
    let mut end = message.len().min(512);
    while !message.is_char_boundary(end) {
        end -= 1;
    }
    message[..end].to_owned()
}

fn account_name_for_display(email: Option<&str>, name: &str) -> String {
    email
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .or_else(|| {
            let trimmed_name = name.trim();
            (!trimmed_name.is_empty()).then_some(trimmed_name)
        })
        .unwrap_or_default()
        .to_owned()
}

#[cfg(test)]
mod tests {
    use super::account_name_for_display;

    #[test]
    fn account_name_prefers_trimmed_email() {
        assert_eq!(
            account_name_for_display(Some("  first@example.com  "), "OPENAI账号"),
            "first@example.com"
        );
    }

    #[test]
    fn account_name_falls_back_to_trimmed_name() {
        assert_eq!(
            account_name_for_display(Some("   "), "  OPENAI账号  "),
            "OPENAI账号"
        );
    }

    #[test]
    fn account_name_allows_empty_fallback() {
        assert_eq!(account_name_for_display(None, "   "), "");
    }
}
