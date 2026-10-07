# Create a baseline with a local agent

In Baselines → Create, enter the URL/models and copy the task. It includes actual detector, interpreter and output paths. No Codex-specific plugin is required. The agent reads bundled SKILL.md, GUIDE.md and RESEARCH_NOTES.md first.

Workflow: confirm scope/budget → separate pilot → analyze/equal-cost selection → formal collection → freeze tier counts and data roles → calibrate and check trajectories → validate → export. Ordinary and other baselines share the predictive scorer; other requires actual external sources.

Version2 tasks propose15 requests per model/probe/window,4 windows and10000 simulated trajectories per tier. These need review; plan sends no requests. Selection coverage, full-run correctness and path-error acceptance are separate frozen settings. Every strong-direction line is capped at98%. Window holdouts require4 nonempty windows. A within-window split must be chosen explicitly and is not temporal or blind validation.

Checks use prefixes of the same answers from60% eligibility onward: missing answers, each delayed probe and a fixed shuffle. Full-run calibration alone is insufficient. Failed candidates are preserved but cannot be exported as passed. More resampling does not fill real coverage gaps.

collect --confirmed still needs prior authorization and hidden local Key entry. Pilot/formal/supplement tasks can share campaign_budget_dir. Actual sends, retries and in-flight attempts consume the same cumulative budget. Known cost is settled; unknown/interrupted requests retain reservations. Unreliable price bounds permit only a request-count guarantee, preferably with a provider account cap. New directories do not authorize resetting spend.

Deliver the importable.meow.json, verification report and non-sensitive provenance. Legacy drafts/collections can be exported without relabeling old answers. Import/default replacement/publication each require a separate choice; local creation does not imply maintainer provenance.
