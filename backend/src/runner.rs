//! Host-owned maintenance call drives persisted jobs; the browser only observes.
use crate::{
    Service,
    domain::{Run, Status},
    host,
    management::{self, excerpt},
    now_ms,
};
use gateway_plugin_sdk::{ErrorCode, PluginFault, client::HostClient};
use std::time::Duration;

const ATTEMPT_BUDGET: Duration = Duration::from_secs(120);
const HANDOFF_MARGIN: Duration = Duration::from_secs(150);

pub(crate) fn queue_time(history: &[(Run, u64)]) -> u64 {
    now_ms().max(
        history
            .iter()
            .filter_map(|(r, _)| r.queued_at)
            .max()
            .unwrap_or(0)
            + 1,
    )
}

pub(crate) fn pause(run: &mut Run, message: &str) {
    if run.status != Status::Stopped {
        run.status = Status::Paused;
    }
    run.queued_at = None;
    run.task_error = Some(excerpt(message));
    run.updated_at = now_ms();
}

/// The shared lock makes initialization a barrier for both management and maintenance.
pub(crate) async fn initialize(service: &Service, host: &HostClient) -> Result<(), PluginFault> {
    let mut state = service.state.lock().await;
    if state.initialized {
        return Ok(());
    }
    let _execution = service.execution.try_acquire().map_err(|_| {
        PluginFault::new(ErrorCode::Capacity, "检测请求正在收尾，请稍后重新读取状态")
    })?;
    let reason = state
        .recovery_reason
        .clone()
        .unwrap_or_else(|| "服务或插件已重启，点击继续检测后重新排队".into());
    for (mut run, version) in management::histories(host).await? {
        if run.finished() {
            continue;
        }
        let interrupted = run.inflight.is_some();
        if interrupted {
            run.recover()?;
        }
        // Existing user pauses keep their reason. No scoring is required to pause.
        if run.status != Status::Paused || interrupted || run.queued_at.is_some() {
            pause(&mut run, &reason);
            if interrupted {
                if let Err(error) = management::update_report(service, &mut run).await {
                    run.task_error = Some(excerpt(&error.message));
                }
            }
            host::write(host, &run, Some(version)).await?;
        }
    }
    state.initialized = true;
    state.recovery_reason = None;
    Ok(())
}

pub(crate) async fn reconcile(service: &Service, host: &HostClient) -> Result<(), PluginFault> {
    let result = cycle(service, host).await;
    if let Err(error) = &result {
        let mut state = service.state.lock().await;
        state.initialized = false;
        state.recovery_reason = Some(excerpt(&format!(
            "后台执行中断：{}；请确认后继续检测",
            error.message
        )));
    }
    result
}

async fn cycle(service: &Service, host: &HostClient) -> Result<(), PluginFault> {
    initialize(service, host).await?;
    loop {
        let remaining = host.remaining_budget().unwrap_or_default();
        if remaining <= HANDOFF_MARGIN {
            return Ok(());
        }
        // Notify retains an enqueue that arrives between reading state and waiting.
        let next = {
            let _lock = service.state.lock().await;
            let mut history = management::histories(host).await?;
            if service.execution.available_permits() > 0 {
                for (run, version) in &mut history {
                    // A cancelled maintenance call may leave a pending attempt in this process.
                    if run.inflight.is_some() {
                        run.recover()?;
                        pause(run, "后台调用中断，当前题结果未知；请确认后继续检测");
                        if let Err(error) = management::update_report(service, run).await {
                            run.task_error = Some(excerpt(&error.message));
                        }
                        host::write(host, run, Some(*version)).await?;
                    }
                }
            }
            history
                .iter()
                .filter(|(r, _)| r.background && r.status == Status::Ready && r.queued_at.is_some())
                .min_by_key(|(r, _)| (r.queued_at, r.created_at, &r.id))
                .map(|(r, _)| r.id.clone())
        };
        let Some(id) = next else {
            // Also discover a committed enqueue if its page call was cancelled
            // immediately after the write, before it could send the local wake-up.
            let wait = (remaining - HANDOFF_MARGIN).min(Duration::from_secs(5));
            let _ = tokio::time::timeout(wait, service.wake.notified()).await;
            continue;
        };
        let Ok(_execution) = service.execution.try_acquire() else {
            tokio::time::sleep(Duration::from_millis(250)).await;
            continue;
        };
        if host.remaining_budget().unwrap_or_default() <= HANDOFF_MARGIN {
            return Ok(());
        }
        // Same per-question limit as the old management call. Ending this parent also
        // closes any abandoned host stream; do not send another question on timeout.
        let result = tokio::time::timeout(
            ATTEMPT_BUDGET,
            management::advance(service, host, &id, true),
        )
        .await;
        match result {
            Ok(Ok(_)) => {}
            other => {
                return Err(match other {
                    Ok(Err(error)) => error,
                    _ => PluginFault::new(
                        ErrorCode::Timeout,
                        "后台单题执行达到 120 秒上限，等待状态恢复",
                    ),
                });
            }
        }
    }
}
