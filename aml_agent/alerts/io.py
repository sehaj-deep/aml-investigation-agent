"""Write and read alert sets as JSON Lines, with a manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aml_agent.alerts.models import Alert, GroundTruth

ALERTS_DIR = Path(__file__).resolve().parents[2] / "evals" / "alerts"


def _write_jsonl(path: Path, records: list) -> str:
    text = "".join(r.model_dump_json() + "\n" for r in records)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_sets(sets: dict, out_dir: Path, meta: dict) -> dict:
    checksums = {}
    for name, alert_set in sets.items():
        checksums[f"{name}.jsonl"] = _write_jsonl(out_dir / f"{name}.jsonl", alert_set.alerts)
        checksums[f"ground_truth/{name}.jsonl"] = _write_jsonl(
            out_dir / "ground_truth" / f"{name}.jsonl", alert_set.truth
        )
    manifest = {**meta, "files": checksums}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", newline="\n")
    return manifest


def read_alerts(name: str, alerts_dir: Path = ALERTS_DIR) -> list[Alert]:
    lines = (alerts_dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [Alert.model_validate_json(line) for line in lines if line]


def read_truth(name: str, alerts_dir: Path = ALERTS_DIR) -> list[GroundTruth]:
    path = alerts_dir / "ground_truth" / f"{name}.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [GroundTruth.model_validate_json(line) for line in lines if line]
