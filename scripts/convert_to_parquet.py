"""Convert the raw HI-Small files in AML_DATA_DIR to Parquet tables in PARQUET_DIR."""

from __future__ import annotations

import json
import time

from aml_agent.data.build import build_all


def main() -> None:
    start = time.perf_counter()
    manifest = build_all()
    print(json.dumps(manifest, indent=2))
    print(f"done in {time.perf_counter() - start:.1f}s")


if __name__ == "__main__":
    main()
