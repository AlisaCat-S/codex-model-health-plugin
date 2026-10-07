# Scoring, baselines and limitations

## Method

The new4.5.3-predictive.2 baselines use the shared meow-fingerprint-v3-predictive engine. Released4.5.2 packages and saved reports are not recalculated. Frozen legacy tasks retain their original contract.

Complete nonempty answers are only stripped/casefolded; noncompliant wording remains an observation. Empty answers and protocol failures do not vote. Malformed usage metadata remains unknown without discarding a complete answer or pretending its cost is zero.

Each valid answer contributes to the run's joint posterior predictive evidence. A question with one answer no longer receives nearly a full heavily sampled question's weight. Each real source/cell has total Dirichlet prior mass1, divided among training categories and one unseen category. Prior mass is not fabricated observations.

Per-cell log evidence is:
`lgamma(sum(a)) - lgamma(sum(a)+sum(n)) + sum(lgamma(a+n)-lgamma(a))`.

Evidence is summed across enabled cells; common multinomial coefficients cancel between sources. other selects the closest single real external source for the whole run, not a per-question mixture. Old S/D/w and family weights are not added. JSD and drift remain offline descriptive tools.

Displayed scores are a sigmoid of the per-valid-answer log advantage over the strongest rival. They are not identity probabilities and need not sum to100%. Only the unique highest candidate may strictly exceed its own full-precision line.

## Counts and eligibility

| Baseline | Quick / Standard / Deep requests | Requests per probe |
|---|---|---|
| GPT,6 probes | 36 / 72 / 108 | 6 / 12 / 18 |
| Claude,6 probes | 60 / 90 / 120 | 10 / 15 / 20 |

Compared with4.5.2, GPT costs80% more planned requests; Claude increases50%,12.5%,0%. This tradeoff must remain visible.

Eligibility is ceil(60%×planned) overall and per cell. Rounding yields minimum totals24/48/66 for GPT and36/54/72 for Claude. Stopping/timeouts do not invalidate qualified evidence. Incomplete sample sets get a brief reliability note. The default shared retry budget remains ceil(planned/2); failed attempts do not vote twice.

## Evidence and its limits

The research refit uses5731 internal raw answers and1971 external answers, without importing old fitted values or lines. Of the external answers,781 were reused and1190 newly collected. The2160-answer target was not fully reached. Qwen's65 sparse answers remain an unfitted diagnostic;8 other external references do not represent every unknown model.

Three development folds calibrate their own vocabulary/prior; the final fit uses their union, excluding original check records. Exact fit, requests, counts, lines and measured checks are bound together. Historical checks were repeatedly inspected during model selection, so this is not new blind validation.

In10000 trajectories per modeled source/tier/pattern, worst full-run correct strong-direction rates were:
- GPT99.51% /99.91% /99.98%.
- Claude99.60% /99.96% /99.94%.

Additional checks cover missing answers, true prefixes, each delayed cell, a fixed shuffle and external-group removal. With final lines frozen, the largest single-pattern all-trajectory false direction among all7 omitted external groups was0.09%. This does not enumerate every network schedule. An alternative chronological split had a GPT low-tier worst full-run result around96.79%; that drift limitation is not hidden by the better split.

The99% full-run goal,99.9% negative selection coverage,98% maximum line and60% sample gate are different quantities. The generic tool also freezes a path-error acceptance bound, default1% among qualified trajectories. A negative quantile is not a joint99.9% risk guarantee. Partial samples may increase refusal; their correctness is not promised to match full runs.

Resampling does not add empirical information. Report errors, insufficient results and qualification denominators. Unqualified paths are not successful identifications. New channels, future drift, answer-correlated missingness and all possible external models remain incompletely covered.

## Protocols, errors and history

Responses uses the last segment's successfully completed full answer; it need not equal accumulated deltas. A failed, refused, blank or truncated last segment never falls back to an earlier answer. Claude and Chat use their respective completion markers. Ordinary failures share retry budgets; cancellation, deadlines and credential/public-address protection remain separate.

HTTP status, in-stream errors and local DNS/TLS/read/decode/timeout failures remain distinct. Error text is bounded and sanitized; missing upstream text is not fabricated, and old missing details are not reconstructed.

Hashes establish integrity, not signatures or model identity. Aliases/URLs are configuration and provenance. A mismatch does not prove deliberate substitution; routing, service behavior or baseline limitations may contribute. The linked[community discussion](https://linux.do/t/topic/2811197)is context, not verified attribution.

## Reproduction

scripts/reproduce.py --check-only validates bundled integrity and calibration bindings. Full reruns require the original campaign task, development/check observations and frozen options; a held-out pool cannot be reconstructed from fitted counts. See[baseline tools](docs/BASELINES_EN.md).
