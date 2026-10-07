# Decisions that need evidence

## Request counts are part of the method

Start with a balanced, varied set of probes and a visible total request budget. Compare selective allocations at the same total cost before accepting them. A large separation statistic is not permission to give one or two answers nearly a full question's influence.

More questions are not automatically better. They can improve coverage, or dilute useful repeats and introduce unstable signals. Preserve rejected variants and distinguish the effect of question selection, allocation and total cost. At partial completion, ceil(60% per cell) can give different actual sample totals even when two profiles share a “60%” label.

## Keep answer handling simple

For new packages, a complete nonempty answer is stripped and casefolded. A response that ignores the requested option or integer range may still contain model information. Do not silently filter such observations or reconstruct missing answers. Empty content, protocol failure, truncation and credential protection are separate operational cases.

Cost/usage metadata is not answer content. Invalid accounting must remain unknown, not zero cost, without discarding an otherwise complete answer.

## Separate three kinds of evidence

- Resampling a fitted pool checks self-consistency. Ten million simulated batches do not create ten million real observations.
- Disjoint records/windows check a fitted candidate on different observations. Repeatedly selecting candidates using that check makes it a development check, not new blind evidence.
- A withheld external source tests behavior when that reference is unavailable. Exclude it from fitting, vocabulary construction and calibration, not merely from a displayed list.

A model outside the candidate set may resemble one candidate. The name returned by a provider does not authenticate its identity; likewise, a mismatch does not identify why the service behaved differently.

## Use development data efficiently without moving the goalposts

A useful option is crossfitted calibration inside a development pool, followed by fitting on the entire development pool and checking the retained check records. Preserve original source, window and record identities. Folds must rebuild their own vocabulary, priors and derived distributions.

A final fit on all observations is also possible, but it is not the same independently checked object. Refit changes predictive concentration and can move scores even if empirical proportions stay the same. Bind and verify the exact exported fitted data and lines; never paste a previous fit's validation label onto a new package.

## Check the whole detection, including stopping

Several independent sample-count draws are not a time series. For path checks, draw each answer once, then evaluate real prefixes of that same sequence. Apply the actual overall/per-cell60% qualification rule.

Inspect normal round-robin completion, missing answers and delayed cells. A named delay pattern only covers that pattern, not all possible network schedules. A fixed-time false-positive rate is not automatically the probability of ever showing a wrong strong result.

Keep one readable decision rule where possible. Strengthening rejection can reduce wrong directions while also discarding valid evidence; report both effects instead of adding successive runtime gates to hide a failing design.

## State denominators and limits

Report separately:
- full-sample correct, wrong and insufficient outcomes;
- partial/stopped outcomes and the fraction that reached sample qualification;
- any-prefix wrong direction, conditional on qualification when relevant;
- errors among issued strong results, not just errors among all trials;
- known internal models, actual reference sources and sparse/unfitted diagnostics.

Unseen sources may appropriately receive insufficient evidence; they do not have to be strongly identified as other. Internal true models being absorbed into other is a different failure and must be checked too.

## Deliver honest, usable artifacts

Call the category other in both languages. It contains actual external reference sources, not invented observations. Each simulated external run has one real source for all questions.

Keep all strong-direction lines at or below98%, and keep the agreed accuracy goals visible. A cap does not prove accuracy. Do not truncate a failing line, lower a target or rename a research JSON to manufacture a usable package.

Deliver the importable .meow.json, exact hashes, count/coverage tables and a short account of the best tested tradeoff. “Best tested” is not globally optimal, independently proven or guaranteed against future distribution shifts. Additional sampling, changing defaults and publication each need their own authority.
