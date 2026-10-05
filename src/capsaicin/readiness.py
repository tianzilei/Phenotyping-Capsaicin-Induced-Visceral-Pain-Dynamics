"""Scientific readiness gates; metadata completeness is not scientific approval."""

import math


def readiness(config):
    reasons = []
    if config.get("identity_verified") is not True:
        reasons.append("identity_and_visit_not_verified")
    if config.get("synchronization_verified") is not True:
        reasons.append("challenge_device_synchronization_not_verified")
    if config.get("units_verified") is not True:
        reasons.append("channel_units_not_verified")
    if config.get("signal_qc_passed") is not True:
        reasons.append("signal_artifact_qc_not_passed")
    if not config.get("roi_mapping"):
        reasons.append("fnirs_roi_mapping_missing")
    if not config.get("primary_outcome") or not config.get("covariate_rationale"):
        reasons.append("association_estimand_and_covariates_not_frozen")
    state = []
    thresholds = config.get("state_thresholds")
    if not isinstance(thresholds, list) or not thresholds:
        state.append("state_thresholds_missing")
    elif any(
        not isinstance(x, (int, float))
        or isinstance(x, bool)
        or not math.isfinite(x)
        or not 0 < x < 10
        for x in thresholds
    ) or thresholds != sorted(set(thresholds)):
        state.append("state_thresholds_invalid")
    if not config.get("state_threshold_rationale"):
        state.append("state_threshold_rationale_missing")
    if not config.get("transition_information_rule"):
        state.append("transition_information_rule_missing")
    if config.get("state_estimator_validated") is not True:
        state.append("state_estimator_not_validated")
    coupling = list(reasons)
    for key in (
        "gastric_peak_verified",
        "phase_quality_verified",
        "adequate_cycles",
        "surrogate_validated",
    ):
        if config.get(key) is not True:
            coupling.append(key + "_not_verified")
    return dict(
        physiology_association=dict(ready=not reasons, reasons=reasons),
        markov=dict(ready=not state, reasons=state),
        coupling=dict(ready=not coupling, reasons=coupling),
    )
