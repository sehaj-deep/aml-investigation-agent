"""Retrieval quality of the guidance lookup: keyword, meaning and hybrid search.

    python evals/guidance_eval.py

A fixed set of questions an AML investigator or the AI reviewer asks, each with the
document that answers it. Reports hit rate at 1 and 3 (the right document among the top
results) and mean reciprocal rank, per search method. Needs the guidance store
(scripts/load_guidance.py) and the local embedding model; uses no language-model quota.
Results go to evals/runs/guidance/.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aml_agent.guidance.search import RRF_K, GuidanceSearch  # noqa: E402

# (question, document that answers it). Written from the documents' topics, not tuned on
# the search results.
QUESTIONS = [
    ("What is a funnel account?", "fincen-fin-2014-a005"),
    ("cash deposits in one state withdrawn quickly in another state", "fincen-fin-2014-a005"),
    ("red flags for funnel account activity", "fincen-fin-2014-a005"),
    ("trade-based money laundering with narcotics proceeds", "fincen-fin-2014-a005"),
    (
        "shell companies with little physical presence used for money laundering",
        "fincen-fin-2006-g014",
    ),
    ("wire transfers through shell companies with no business purpose", "fincen-fin-2006-g014"),
    (
        "foreign correspondent bank wire transfer volume above the expected profile",
        "fincen-fin-2006-g014",
    ),
    ("what should a SAR narrative contain: who, what, when, where and why", "fincen-sar"),
    ("how to describe why the activity is unusual for the customer", "fincen-sar"),
    ("common errors in suspicious activity report narratives", "fincen-sar-common-errors"),
    ("do not write see attached in the narrative", "fincen-sar"),
    ("funds transfers with no logical business or economic purpose", "ffiec-appendix-f"),
    ("customer provides insufficient or suspicious identification", "ffiec-appendix-f"),
    ("structuring cash deposits to avoid reporting requirements", "ffiec-appendix-f"),
    ("transactions with higher-risk jurisdictions or secrecy havens", "ffiec-appendix-f"),
    ("many funds transfers sent in large round dollar amounts", "ffiec-appendix-f"),
    ("rapid movement of funds in and out of an account", "ffiec-appendix-f"),
    ("activity inconsistent with the customer's business", "ffiec-appendix-f"),
]


def rank_of(ids: list[str], doc: str) -> int | None:
    return next((i for i, pid in enumerate(ids, start=1) if pid.startswith(doc)), None)


def fused(rankings: list[list[str]]) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, pid in enumerate(ranking, start=1):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores, key=lambda pid: (-scores[pid], pid))


def main() -> None:
    g = GuidanceSearch()
    methods: dict[str, list[int | None]] = {"keyword": [], "meaning": [], "hybrid": []}
    rows = []
    for question, doc in QUESTIONS:
        kw, sem = g.keyword(question), g.semantic(question)
        ranks = {
            "keyword": rank_of(kw, doc),
            "meaning": rank_of(sem, doc),
            "hybrid": rank_of(fused([kw, sem]), doc),
        }
        for m, r in ranks.items():
            methods[m].append(r)
        rows.append({"question": question, "expected": doc, **ranks})
        print(
            f"{doc:28} kw={ranks['keyword']} sem={ranks['meaning']} "
            f"hyb={ranks['hybrid']}  {question}"
        )
    summary = {}
    for m, ranks in methods.items():
        n = len(ranks)
        summary[m] = {
            "hit_at_1": round(sum(1 for r in ranks if r == 1) / n, 3),
            "hit_at_3": round(sum(1 for r in ranks if r and r <= 3) / n, 3),
            "mrr": round(sum(1 / r for r in ranks if r) / n, 3),
        }
    print(json.dumps(summary, indent=1))
    out = ROOT / "evals" / "runs" / "guidance"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"guidance-{stamp}.json"
    path.write_text(
        json.dumps(
            {"created_utc": stamp, "questions": len(QUESTIONS), "summary": summary, "rows": rows},
            indent=1,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"written {path}")


if __name__ == "__main__":
    main()
