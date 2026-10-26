use crate::invalid;
use gateway_plugin_sdk::PluginFault;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const SLOTS: usize = 16;

#[derive(Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Method {
    #[default]
    Meow,
    ModelTrace,
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AccountIdentity {
    pub authentication_kind: String,
    pub upstream_user_id: Option<String>,
    pub upstream_account_id: Option<String>,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Run {
    pub id: String,
    pub slot: usize,
    pub created_at: u64,
    pub updated_at: u64,
    pub account_id: String,
    pub account_name: String,
    pub credential_revision: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub account_identity: Option<AccountIdentity>,
    pub key_id: String,
    pub key_name: String,
    pub plan: Value,
    pub status: Status,
    pub attempts: Vec<Value>,
    pub inflight: Option<String>,
    pub report: Value,
    /// Opt-in keeps existing single-step API clients usable.
    #[serde(default)]
    pub background: bool,
    #[serde(default)]
    pub queued_at: Option<u64>,
    #[serde(default)]
    pub task_error: Option<String>,
}

#[derive(Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Debug)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Ready,
    Running,
    Paused,
    Completed,
    Stopped,
}

impl Run {
    pub fn finished(&self) -> bool {
        matches!(self.status, Status::Completed | Status::Stopped) && self.inflight.is_none()
    }
    pub fn jobs(&self) -> &[Value] {
        self.plan["jobs"]
            .as_array()
            .map(Vec::as_slice)
            .unwrap_or(&[])
    }
    pub fn successful(&self, job: &str) -> bool {
        self.attempts
            .iter()
            .any(|a| a["job_id"] == job && a["status"] == "ok")
    }
    pub fn next_job(&self) -> Option<String> {
        let ids: Vec<_> = self
            .jobs()
            .iter()
            .filter_map(|j| j["job_id"].as_str())
            .collect();
        if let Some(id) = ids
            .iter()
            .find(|id| !self.attempts.iter().any(|a| a["job_id"] == **id))
        {
            return Some((*id).into());
        }
        let retries = self.attempts.len().saturating_sub(ids.len());
        if retries >= self.plan["retry_budget"].as_u64().unwrap_or(0) as usize {
            return None;
        }
        ids.into_iter()
            .find(|id| !self.successful(id))
            .map(str::to_owned)
    }
    pub fn reserve(&mut self, job: &str) -> Result<(), PluginFault> {
        if self.status != Status::Ready || self.inflight.is_some() {
            return Err(invalid("任务未就绪；请刷新状态后继续"));
        }
        if self.next_job().as_deref() != Some(job) {
            return Err(invalid("检测题目顺序发生变化"));
        }
        self.attempts
            .push(json!({"job_id":job,"status":"pending","error":null}));
        self.inflight = Some(job.into());
        self.status = Status::Running;
        Ok(())
    }
    pub fn finish_attempt(&mut self, mut result: Value) -> Result<(), PluginFault> {
        let job = self
            .inflight
            .take()
            .ok_or_else(|| invalid("没有待完成的检测请求"))?;
        result["job_id"] = json!(job);
        let last = self
            .attempts
            .last_mut()
            .ok_or_else(|| invalid("缺少检测尝试记录"))?;
        if last["status"] != "pending" || last["job_id"] != job {
            return Err(invalid("检测尝试记录不一致"));
        }
        *last = result;
        if matches!(self.status, Status::Stopped | Status::Paused) {
            self.queued_at = None;
            return Ok(());
        }
        self.status = if self.next_job().is_none() {
            Status::Completed
        } else if self.attempts.last().is_some_and(|a| a["status"] == "error") {
            Status::Paused
        } else {
            Status::Ready
        };
        if self.status != Status::Ready {
            self.queued_at = None;
        }
        Ok(())
    }
    pub fn recover(&mut self) -> Result<(), PluginFault> {
        if self.inflight.is_some() {
            self.finish_attempt(json!({"status":"error","error":"interrupted_unknown_result","answer":"","request_id":null}))?;
        }
        if !self.finished() {
            self.status = if self.next_job().is_some() {
                Status::Ready
            } else {
                Status::Completed
            };
        }
        Ok(())
    }
    pub fn summary(&self) -> Value {
        json!({"id":self.id,"created_at":self.created_at,"updated_at":self.updated_at,
            "account_name":self.account_name,"account_id":self.account_id,"key_name":self.key_name,
            "request_model":self.plan["request_model"],"claimed_model":self.plan["claimed_model"],
            "method":self.plan.get("method").cloned().unwrap_or_else(|| json!("meow")),
            "tier":self.plan["tier"],"baseline_hash":self.plan["hash"],"status":self.status,
            "attempts":self.attempts.len(),"planned":self.jobs().len(),"report":self.report,
            "background":self.background,"queued_at":self.queued_at,"task_error":self.task_error})
    }
}

pub fn slot_from_id(id: &str) -> Result<usize, PluginFault> {
    let slot = id
        .split('-')
        .next()
        .and_then(|s| s.parse::<usize>().ok())
        .filter(|s| *s < SLOTS);
    if id.len() > 100 || !id.bytes().all(|b| b.is_ascii_digit() || b == b'-') {
        return Err(invalid("任务 ID 格式错误"));
    }
    slot.ok_or_else(|| invalid("任务 ID 格式错误"))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn run() -> Run {
        Run {
            id: "0-1".into(),
            slot: 0,
            created_at: 0,
            updated_at: 0,
            account_id: "a".into(),
            account_name: "a".into(),
            credential_revision: 1,
            account_identity: None,
            key_id: "k".into(),
            key_name: "k".into(),
            plan: json!({"jobs":[{"job_id":"a"},{"job_id":"b"}],"retry_budget":1}),
            status: Status::Ready,
            attempts: vec![],
            inflight: None,
            report: Value::Null,
            background: false,
            queued_at: None,
            task_error: None,
        }
    }
    #[test]
    fn pause_survives_completion() {
        let mut r = run();
        r.reserve("a").unwrap();
        r.status = Status::Paused;
        r.finish_attempt(json!({"status":"ok"})).unwrap();
        assert_eq!(r.status, Status::Paused);
    }
    #[test]
    fn interrupted_attempts_are_charged() {
        let mut r = run();
        r.reserve("a").unwrap();
        r.recover().unwrap();
        assert_eq!(r.attempts.len(), 1);
        assert_eq!(r.next_job().as_deref(), Some("b"));
    }
    #[test]
    fn retry_budget_does_not_skip_unsent_jobs() {
        let mut r = run();
        for job in ["a", "b", "a"] {
            r.status = Status::Ready;
            r.reserve(job).unwrap();
            r.finish_attempt(json!({"status":"error"})).unwrap();
        }
        assert_eq!(r.status, Status::Completed);
        assert!(r.next_job().is_none());
    }
    #[test]
    fn stop_survives_completion() {
        let mut r = run();
        r.reserve("a").unwrap();
        r.status = Status::Stopped;
        r.finish_attempt(json!({"status":"ok"})).unwrap();
        assert!(r.finished());
    }
    #[test]
    fn duplicate_dispatch_is_rejected() {
        let mut r = run();
        r.reserve("a").unwrap();
        assert!(r.reserve("a").is_err());
    }

    #[test]
    fn probability_survives_json_state_roundtrip() {
        let value = json!({"probability":1.1494210082389823e-7_f64});
        let restored: Value = serde_json::from_slice(&serde_json::to_vec(&value).unwrap()).unwrap();
        assert_eq!(restored, value);
    }
}
