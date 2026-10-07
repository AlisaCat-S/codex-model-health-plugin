"""Whole-run posterior predictive comparison; shared by desktop and website."""
import math
import numpy as np

SCORING_VERSION = "meow-fingerprint-v3-predictive"
OTHER_ID = "other_known_external"
UNKNOWN = "__UNSEEN_IN_TRAINING__"


def _increments(alpha, maximum):
    return np.asarray([[math.lgamma(a + n) - math.lgamma(a) for n in range(maximum + 1)]
                       for a in alpha])


class PredictiveScorer:
    """Compile a fixed reference once, then evaluate real or simulated prefixes."""
    def __init__(self, fitted, maximum_counts):
        self.fitted = fitted
        self.tables = {}
        for identity, maximum in maximum_counts.items():
            cell = fitted["cells"][identity]
            alpha = [cell["alpha"][source] for source in fitted["sources"]]
            numerator = np.asarray([_increments(a, maximum) for a in alpha])
            denominator = np.asarray([[math.lgamma(sum(a)) - math.lgamma(sum(a) + n)
                                       for n in range(maximum + 1)] for a in alpha])
            self.tables[identity] = numerator, denominator

    def matches(self, draws):
        """Public multinomial coefficients cancel; every answer enters the joint fit."""
        fitted = self.fitted
        size = len(next(iter(draws.values()))) if draws else 1
        sources = fitted["sources"]
        evidence = np.zeros((size, len(sources)))
        total = np.zeros(size, dtype=np.int64)
        for identity in sorted(draws):
            counts = np.asarray(draws[identity], dtype=np.int64)
            n = counts.sum(axis=1)
            total += n
            numerator, denominator = self.tables[identity]
            value = denominator[:, n].T.copy()
            for c in range(counts.shape[1]):
                value += numerator[:, c, counts[:, c]].T
            evidence += value
        positions = {source: i for i, source in enumerate(sources)}
        values = {}
        for model in fitted["models"]:
            if model != OTHER_ID:
                values[model] = evidence[:, positions[model]]
                continue
            reference = evidence[:, [positions[s] for s in fitted["reference_sources"]]]
            peak = reference.max(axis=1)
            values[model] = peak if fitted["aggregation"] == "nearest_source" else (
                peak + np.log(np.exp(reference - peak[:, None]).mean(axis=1)))
        matrix = np.column_stack([values[m] for m in fitted["models"]])
        ordered = np.sort(matrix, axis=1)
        rival = np.where(matrix == ordered[:, -1, None], ordered[:, -2, None], ordered[:, -1, None])
        divisor = np.maximum(total[:, None], 1)
        return np.exp(-np.logaddexp(0, (rival - matrix) / divisor)), matrix / divisor


def numeric_matches(fitted, draws):
    maximum = {c: int(np.asarray(x).sum(axis=1).max()) for c, x in draws.items()}
    return PredictiveScorer(fitted, maximum).matches(draws)


def fit_observations(observations, models, cells, reference=None):
    """Fit actual internal/external counts; keep the prior distinct from samples."""
    from collections import Counter
    from .errors import AppError
    internal = [m for m in models if m != OTHER_ID]
    external = []
    if OTHER_ID in models:
        if not isinstance(reference, dict) or reference.get("id") != OTHER_ID or reference.get("method") != "fixed_source_predictive_v1":
            raise AppError("invalid_virtual_reference")
        external = reference.get("sources")
        if (not isinstance(external, list) or not 1 <= len(external) <= 32
                or any(not isinstance(s, str) or not s or len(s) > 256 for s in external)
                or len(set(external)) != len(external) or set(external) & set(models)
                or set(reference.get("counts", {})) != set(cells)):
            raise AppError("invalid_virtual_reference")
    elif reference is not None:
        raise AppError("invalid_virtual_reference")
    fitted = {"scoring_version": SCORING_VERSION, "prior_mass": 1.0,
              "models": list(models), "sources": internal + external,
              "reference_sources": list(external), "aggregation": "nearest_source", "cells": {}}
    for identity, cell in cells.items():
        if OTHER_ID in observations.get(identity, {}):
            raise AppError("virtual_reference_has_observations")
        counts = {}
        for model in internal:
            counts[model] = Counter()
            for window in observations.get(identity, {}).get(model, {}).values():
                counts[model].update(window["counts"])
        if external:
            supplied = reference["counts"][identity]
            if not isinstance(supplied, dict) or set(supplied) != set(external):
                raise AppError("invalid_virtual_reference")
            counts.update({source: Counter(supplied[source]) for source in external})
        for values in counts.values():
            for category, number in values.items():
                if (not isinstance(category, str) or len(category.encode("utf-8")) > 4096
                        or type(number) is not int or not 0 <= number <= 100000000
                        or category != "__INVALID_OUTPUT__" and (not category or category != category.strip().casefold())):
                    raise AppError("invalid_observations", field=identity)
            values.pop("__INVALID_OUTPUT__", None)
        categories = sorted({UNKNOWN} | {c for values in counts.values() for c, n in values.items() if n})
        alpha = {source: [counts[source][c] + 1 / len(categories) for c in categories]
                 for source in fitted["sources"]}
        totals = {source: sum(counts[source].values()) for source in fitted["sources"]}
        fitted["cells"][identity] = {"categories": categories, "alpha": alpha,
                                    "source_samples": totals, "reference_ready": all(totals.values())}
    return fitted


def score_counts(fitted, counts, planned, thresholds=None, *, calibrated=True,
                 claimed_model=None, completion_ratio=.6):
    from collections import Counter
    models = fitted["models"]
    details, draws, reasons = {}, {}, []
    for identity, requested in planned.items():
        if not requested:
            continue
        cell = fitted["cells"].get(identity)
        if not cell or not cell["reference_ready"]:
            reasons.append("baseline_cell_missing")
            continue
        normalized = Counter()
        invalid = 0
        for category, number in counts.get(identity, {}).items():
            if category == "__INVALID_OUTPUT__":
                invalid += number
            else:
                normalized[category if category in cell["categories"] else UNKNOWN] += number
        valid = sum(normalized.values())
        minimum = math.ceil(completion_ratio * requested)
        if valid < minimum:
            reasons.append("samples_incomplete")
        if valid + invalid > requested:
            reasons.append("samples_exceed_plan")
        draws[identity] = np.asarray([[normalized[c] for c in cell["categories"]]], dtype=np.int64)
        details[identity] = {"planned": requested, "minimum": minimum, "completed": valid + invalid,
                             "valid": valid, "counts": dict(normalized)}
    total = sum(c["valid"] for c in details.values())
    budget = sum(planned.values())
    insufficient = total < math.ceil(budget * completion_ratio)
    if not total:
        reasons.append("no_valid_samples")
    if insufficient:
        reasons.append("samples_incomplete")
    if not calibrated or not thresholds or set(thresholds) != set(models):
        reasons.append("uncalibrated")
    if claimed_model is not None and claimed_model not in models:
        reasons.append("unknown_claimed_model")
    relative, log_fit = numeric_matches(fitted, draws)
    matches = {m: float(relative[0, i]) for i, m in enumerate(models)}
    scores = {m: float(log_fit[0, i]) for i, m in enumerate(models)}
    for cell in details.values():
        cell["weight"] = cell["valid"] / total if total else 0.0
    winner = max(models, key=matches.get)
    if not reasons:
        if sum(matches[m] == matches[winner] for m in models) != 1:
            reasons.append("multiple_thresholds")
        elif matches[winner] <= thresholds[winner]:
            reasons.append("no_threshold")
    if reasons:
        winner = None
    verdict = "insufficient" if winner is None else "match" if winner == claimed_model else "mismatch"
    return {"scoring_version": SCORING_VERSION, "verdict": verdict,
            "color": {"match": "green", "mismatch": "red", "insufficient": "yellow"}[verdict],
            "model": winner, "claimed_model": claimed_model, "reasons": sorted(set(reasons)),
            "matches": matches, "scores": scores, "thresholds": thresholds or {},
            "cells": details, "families": {}, "valid_samples": total, "planned_samples": budget,
            "sample_policy": {"version": "60-percent-v1", "overall_ratio": completion_ratio,
                              "per_cell_ratio": completion_ratio},
            "partial_samples": total < budget,
            "quality_status": "insufficient_valid_samples" if insufficient else "cell_samples_incomplete" if "samples_incomplete" in reasons else "sufficient"}
