"""Rules-based behavioral risk indicators (roadmap phase B), explainable by design.

Each rule is a recognized red flag in AML guidance, checked on an account's own
transfers in the review period (non-self, primary period, payment format never
used). An account's score is the sum of the weights of the rules it fires. A case's
risk score is the subject's score plus the highest score among its first-time
counterparties: in a laundering network the subject is often an ordinary-looking
member, and the giveaway sits one step away.

Measured on a sample excluding every evaluation-set account and block (100
laundering accounts from dev and unused pattern blocks, 95 activity-matched ordinary
accounts): subject score alone AUC 0.763, subject plus the riskiest first-time
counterparty AUC 0.906. Bands: high at 7 or more (flags 54% of laundering, 5% of
ordinary accounts), medium at 5 to 6 (90% and 21% at 5 or more), low below 5. These
thresholds were chosen on that sample; the frozen evaluation set gives the honest
figure. Signals such as currency conversion are especially clean in this simulator,
and must be reported that way.
"""

from __future__ import annotations

from dataclasses import dataclass

HIGH_BAND = 7
MEDIUM_BAND = 5

# Signal thresholds, shared with the set-based population scorer (population.py).
NEW_COUNTERPARTY_MIN = 0.9
ONE_TIME_COUNTERPARTY_MIN = 0.7
PERIOD_ACTIVITY_MIN = 0.7
ONWARD_24H_MIN = 0.5
ONE_TIME_MAX_TRANSFERS = 2
MAX_RISK_COUNTERPARTIES = 8


@dataclass(frozen=True)
class Rule:
    code: str
    weight: int
    title: str
    description: str


RULES: tuple[Rule, ...] = (
    Rule(
        "R1",
        3,
        "Currency conversion pass-through",
        "Receives funds in one currency and pays out only in other currencies.",
    ),
    Rule(
        "R2",
        1,
        "Flow-through activity",
        "Both receives and pays out funds in the review period.",
    ),
    Rule(
        "R3",
        1,
        "Predominantly new counterparties",
        "At least 90% of counterparties in the review period were never seen before it.",
    ),
    Rule(
        "R4",
        1,
        "Predominantly one-time relationships",
        "At least 70% of counterparties transact only once or twice in the review period.",
    ),
    Rule(
        "R5",
        1,
        "Activity concentrated in the review period",
        "At least 70% of the account's primary-period transactions fall in the review period.",
    ),
    Rule(
        "R6",
        1,
        "Rapid onward transfers",
        "At least half of incoming transfers are followed by an outgoing payment within 24 hours.",
    ),
)
RULE_BY_CODE = {r.code: r for r in RULES}


def fired_rules(signals: dict) -> list[str]:
    """Codes of the rules an account's behavior signals fire."""
    if not signals or signals.get("n_transfers", 0) == 0:
        return []
    fired = []
    if signals["currency_switch"]:
        fired.append("R1")
    if signals["receives_and_pays"]:
        fired.append("R2")
    if signals["new_counterparty_share"] >= NEW_COUNTERPARTY_MIN:
        fired.append("R3")
    if signals["one_time_counterparty_share"] >= ONE_TIME_COUNTERPARTY_MIN:
        fired.append("R4")
    if signals["period_activity_share"] >= PERIOD_ACTIVITY_MIN:
        fired.append("R5")
    if signals["onward_within_24h_share"] >= ONWARD_24H_MIN:
        fired.append("R6")
    return fired


def account_score(codes: list[str]) -> int:
    return sum(RULE_BY_CODE[c].weight for c in codes)


def band(score: int) -> str:
    if score >= HIGH_BAND:
        return "high"
    if score >= MEDIUM_BAND:
        return "medium"
    return "low"


def case_risk(subject: dict, counterparties: dict[str, dict]) -> dict:
    """Case risk from the subject's signals and its first-time counterparties' signals.

    `counterparties` maps a case-file label to that account's behavior signals.
    """
    subject_codes = fired_rules(subject)
    subject_score = account_score(subject_codes)
    scored = {
        label: (account_score(fired_rules(s)), fired_rules(s))
        for label, s in counterparties.items()
    }
    top_label, (top_score, top_codes) = max(
        scored.items(), key=lambda kv: (kv[1][0], kv[0]), default=(None, (0, []))
    )
    total = subject_score + top_score
    return {
        "score": total,
        "band": band(total),
        "subject": {"score": subject_score, "rules": subject_codes},
        "top_counterparty": (
            {"label": top_label, "score": top_score, "rules": top_codes} if top_label else None
        ),
        "counterparties": {k: {"score": v[0], "rules": v[1]} for k, v in scored.items()},
    }


def describe(risk: dict, subject_label: str = "A0") -> str:
    """Case-file section with the risk score and the reasons behind it."""
    lines = [
        f"Risk indicators (rules; score {risk['score']}, band {risk['band'].upper()}; "
        f"high at {HIGH_BAND} or more, medium at {MEDIUM_BAND} to {HIGH_BAND - 1}):"
    ]

    def reasons(codes: list[str]) -> str:
        if not codes:
            return "no rule fired"
        return "; ".join(f"{c} {RULE_BY_CODE[c].title} (+{RULE_BY_CODE[c].weight})" for c in codes)

    lines.append(
        f"Subject {subject_label}: score {risk['subject']['score']}: "
        f"{reasons(risk['subject']['rules'])}."
    )
    top = risk.get("top_counterparty")
    if top and top["score"] > 0:
        lines.append(
            f"Riskiest first-time counterparty {top['label']}: score {top['score']}: "
            f"{reasons(top['rules'])}."
        )
    others = [
        f"{k} {v['score']}"
        for k, v in sorted(risk["counterparties"].items())
        if top and k != top["label"]
    ]
    if others:
        lines.append(f"Other first-time counterparties checked (score): {', '.join(others)}.")
    lines.append("Rule scores are evidence for your judgment, not a verdict.")
    return "\n".join(lines)
