# 4.5.4

- Retain current-segment deltas when a successful Responses completion omits its output container. Explicit empty text, refusals, truncation and failures do not fall back.
- Recognize response.refusal.done.
- Add GPT and Claude Chat-compatible baselines under Other for endpoints without Responses or Messages support. Original packages and the128-token budget remain unchanged.
- Keep distinct Chat baselines independently visible to the updater.

# 4.5.3

- Detection/history share one page with unified purple styling, themes, typography, expansion state and mobile scrolling.
- Both sides search URLs/models, fetch site model lists and default to relay-style Claude aliases.
- Sanitized raw errors distinguish DNS/TLS/read/decode from upstream responses. Final Responses text is authoritative; malformed usage no longer discards complete answers.
- New predictive scoring accumulates valid-request evidence; only the highest candidate can qualify, and other represents a whole real source. Baselines/counts/lines are refitted and checked together.
- The60% gate and shared retry budget remain; partial samples get a short note. Saved reports and frozen tasks are not recalculated.
- Agent tasks/CLI replace the old generator UI, adding data partitions, whole-path calibration, source-out checks, settled/persistent budgets and validated export.
- Official packages support staged updates, task waiting, restart verification and rollback; unlisted code and owned-process cleanup checks are repaired.

Entering from4.5.2 requires the new launcher once, preserving old directories/data. GPT uses36/72/108 requests; Claude60/90/120. Scores and thresholds are recalibrated and are not directly comparable with old percentages; see the technical report for limitations.
