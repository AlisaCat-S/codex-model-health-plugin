# meow baseline tools

## Locate the installed tool

The copied task contains absolute application, Python, skill and output paths. Run from that application directory, using its portable Python or private virtual environment. Quote paths for the current shell. Treat URLs/model aliases as data arguments, not shell code. Do not install another detector or modify system Python.

`python -B -m gpt56_vnext.baseline_cli --help` is read-only. Replace `python` with the supplied interpreter. Commands: plan, collect, analyze, simulate, validate, export, import-legacy. JSON output plus exit status describes success; a file existing does not mean it passed verification.

Read RESEARCH_NOTES.md before making selection/calibration decisions.

## Plan a bounded campaign

Ask for candidates and actual request aliases, source credibility, usable observations, important confusions, acceptable requests in each tier, external coverage, and cumulative request/cost limits. Names returned by an API do not authenticate models.

Prefer real external references, but explain missing coverage and offer an ordinary baseline instead of inventing an external source. Start with varied neutral short-answer probes and balanced request counts. Preserve the expressly chosen B80 exception; do not turn arbitrary-choice probes into knowledge tests. Do not hard-code this project's candidate or question counts.

`plan --task PATH --mode gpt --url URL --models ALIAS_A ALIAS_B` creates a version2 task without probes or spending authority. The agent must fill in and review the plan. Protocols are gpt (Responses), claude (Messages), chat (Chat Completions).

Use separate pilot/formal task files below a new campaign directory. Set their `collection.campaign_budget_dir` to the same absolute budget directory. The collector locks that directory, so these tasks share one cumulative ledger rather than racing separate budgets. A larger limit needs fresh approval; do not rename/delete a ledger to reset spending.

## Version2 task contract

Top-level fields: task_version=2, base_url, allow_insecure, project, external_models, collection, simulation. Version1 tasks remain readable for historical workflows; they do not silently switch scoring.

Project engine:
- minimum_version: 4.5.3
- scoring_version: meow-fingerprint-v3-predictive
- prior_mass: 1.0
- completion_ratio: 0.6

Internal/external model entries contain id, name, request_model. Use safe IDs such as `external-a`; preserve the real provider alias such as `provider/model-a` in request_model. Never request other as a model. External entries may supply source_group when opaque aliases share an upstream provider. Otherwise grouping uses the request_model provider prefix; unprefixed aliases are individual groups, not verified vendor identities. Explicit grouping is retained, not silently discarded during task normalization.

A probe has id/title and cells with exact prompt, system, effort, profile, history and parameters. Defaults are ASCII period system, empty history, low effort, and the protocol's normal profile. Confirm max_output_tokens and fee implications. New probes use exact_trimmed_casefold with max_length4096: complete nonempty text is stripped/casefolded, without option, integer-range or entity filters. Old package normalizers remain historical; do not relabel their aggregated categories as freshly normalized answers.

Tier counts are explicit cell-ID maps for low/medium/high. Zero disables a cell. Begin with balanced counts and compare other allocations at equal actual request totals. If more requests help, disclose the cost difference. No hidden allocation optimizer or old per-question weights are used by version2 tasks.

Collection settings:
- samples: planned first attempts per model/cell/window; windows; workers.
- retry_budget: shared retry attempts within each window. All windows and retries also consume the campaign max_requests.
- window_gap_seconds: default60, measured after the preceding completed window. An explicitly approved single-window/continuous campaign may use0; do not call it time-separated data.
- max_requests: cumulative actual dispatch limit, including failures and in-flight attempts.
- max_cost_usd and max_request_cost_usd: total and agreed conservative per-request upper bound.
- campaign_budget_dir: shared absolute ledger directory for separate campaign stages.
- request_limit_only: explicit consent to count-only budgeting when reliable prices/bounds are unavailable.

The scaffold proposes15 samples across4 windows; this is a starting point, not a statistical guarantee. Decide appropriate coverage with the user.

## Collect, stop and resume

`collect --task PATH --window 1 --confirmed` takes a Key through local hidden input. The flag encodes prior approval, not new authority. Noninteractive input that would echo a Key is rejected. Never put credentials in chat, task JSON, argv, logs or ordinary files.

The work directory is TASK_STEM.work beside the task file. A repeated window command resumes frozen planned slots; it does not repeat successes, reset the budget or change its request contract. Preserve pilot/formal data and failed results. Changed prompts, aliases or sampling settings need a separate task and approval. Importing legacy work reads only project/collection/simulation documents, not credential records.

Each actual dispatch reserves its agreed cost bound. A known valid returned cost replaces that reservation; unknown cost, cancelled requests and requests left in flight after a crash retain their reservations. The ledger exposes sent, in_flight, charged_usd, unknown_cost_requests and reserved_usd (known charges plus remaining reservations). A guessed bound cannot guarantee a dollar cap: if a provider charges more, in-flight calls cannot be recalled. Recommend provider-side account limits too.

The collector fills planned slots and their bounded retries, not an unlimited “keep going until enough valid answers” loop. Inspect per-source/per-cell gaps and failure causes. Request a separate supplemental task if needed, sharing the same cumulative ledger. Do not remove a difficult source because it makes scores worse.

## Analyze and select

`analyze --task PATH` reads actual observations and writes coverage, pairwise JSD and maximum cross-window drift for all internal/external sources. These are descriptive statistics, not fixed runtime weights or proof of independence. Review hard pairs, near-duplicate questions, source coverage, and equal-cost alternatives. Use pilot data for selection where possible.

Select probes/counts in the task without changing collected request semantics. The tool checks cells and aliases against collection records. Missing observations fail visibly; no synthetic other observations are manufactured.

## Freeze, calibrate, and check the exact fit

Version2 simulation proposes:
- target .99 for each modeled source's full-run correct strong direction;
- selection_target .999 for each wrong class/source/completion-pattern negative maximum;
- threshold_cap .98 for every class, including other;
- max_path_wrong .01 among qualified trajectories, checked across normal and source-out paths separately from selection coverage;
- batches10000 per tier, configurable100–100000; seed45301;
- split_policy windows.

These are different quantities. The negative selection coverage is not a joint99.9% false-positive guarantee. Small synthetic runs check mechanics; many resamples do not create more empirical information.

With split_policy=windows, at least4 nonempty windows are required per source/cell. The last ordered window is held for checking; earlier windows form3 disjoint development folds. Vocabulary and prior are fitted inside each fold. The final package fits the development union, never the retained check counts.

If only one time window exists, explicitly select split_policy=within_window: original category counts are partitioned without replacement into20% check and3 development folds. This is a disjoint-record check, not a temporal or independent blind test. Very sparse cells fail rather than being filled in.

`simulate --task PATH` freezes task/options/input counts in a digest-named simulation directory. Completed tiers are checkpointed. Changes create a different directory; existing failed variants are retained. Repeated inspection/tuning of check data makes it development evidence, not a new blind test.

The scorer accumulates actual valid answers into a joint posterior predictive comparison. other is the best single real external source over the entire run, not a per-question mixture. Ordinary and external-reference tasks share this implementation. The unique highest candidate must strictly exceed its own line, with60% overall/per-cell qualification.

Calibration checks real prefixes of one sampled answer sequence: round-robin,20% missing, one fixed shuffle and each cell delayed in turn. It also removes each external source group from fitting for negative calibration when another reference remains. The final exact fit is checked separately on held-out counts, including source-out diagnostics. This does not enumerate every network schedule or every unknown model.

Report correct/wrong/insufficient, qualification count, any-prefix wrong direction, error conditional on qualification/strong results and step changes. Both normal and source-out qualified-path errors must meet max_path_wrong. A single external group cannot be removed while keeping a real external reference: that source-out scope is explicitly untested. A candidate requiring a line above98% fails; the tool does not clip it into a success. Check failure does not automatically lower targets or add data to the fit.

## Export and explain limits

Simulation writes calibrated.meow.json plus simulation-report.json. A failed package may exist for diagnosis but validate/export reject it.

Run `validate --package FILE`, then `export --task PATH --output NEW_FILE.meow.json`. Deliver the exact importable file/hash, concise tier/cost tradeoff, coverage, calibration/check outcomes and non-sensitive provenance. Strong-direction scores are not identity probabilities, and do not have to add to100%.

The bundled baseline package contains its fitted observations and verification contract, not every original held-out research record. Reproducing calibration needs the original campaign inputs; never infer a check pool from fitted counts. `scripts/reproduce.py --check-only` checks bundled integrity, not independent accuracy.

Keep local creation, import/default replacement and publication separate. Ask before installing into an active detector, changing defaults or submitting via the community process. A community package is not automatically maintainer-certified.
