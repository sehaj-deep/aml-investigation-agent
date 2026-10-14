"""Generate the seeded dev and evaluation alert sets into evals/alerts/."""

from __future__ import annotations

import argparse
import json

from aml_agent import config
from aml_agent.alerts import generate as gen
from aml_agent.alerts.io import ALERTS_DIR, write_sets
from aml_agent.data.views import connect

DEFAULT_SEED = 20261014
VERSION = "v2"  # v2: only patterns that finish by 2022-09-10; windows clipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    con = connect()
    sets = gen.generate(con, seed=args.seed)
    parquet_manifest = json.loads((config.parquet_dir() / "MANIFEST.json").read_text())
    meta = {
        "version": VERSION,
        "seed": args.seed,
        "dev_per_type": gen.DEV_PER_TYPE,
        "eval_per_type": gen.EVAL_PER_TYPE,
        "window_padding_hours": gen.WINDOW_PADDING.total_seconds() / 3600,
        "primary_period_only": True,
        "source_seed_eligible_sha256": parquet_manifest["outputs"]["seed_eligible.parquet"],
    }
    manifest = write_sets(sets, ALERTS_DIR, meta)
    for name, s in sets.items():
        n_pos = sum(t.label == "positive" for t in s.truth)
        n_late = sum(t.runs_past_primary_period for t in s.truth)
        print(f"{name}: {len(s.alerts)} alerts ({n_pos} positive), {n_late} run past 09/10")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
