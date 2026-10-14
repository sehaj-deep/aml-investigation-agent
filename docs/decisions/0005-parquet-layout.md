# 0005 Parquet layout and determinism

Status: accepted (Sprint 0)

`scripts/convert_to_parquet.py` writes these tables to `PARQUET_DIR` (gitignored): `transactions`, `accounts`, `banks`, `pattern_blocks`, `pattern_transactions`, `other_laundering`, `pattern_accounts`, `seed_eligible`, plus `MANIFEST.json` with sha256 checksums.

- `tx_id` is the 1-based row of `HI-Small_Trans.csv`: read with `parallel = false`, insertion order preserved, `row_number()`. An independent test streams the raw CSV with the `csv` module and compares 1,002 rows.
- Amounts are `DECIMAL(24,6)` (the file has at most 6 decimals); never floats.
- Bank IDs are kept raw (`*_bank_raw`) and as integers (`from_bank`, `to_bank`); joins use the integers.
- One thread, fixed row-group size and zstd: two runs give byte-identical files (checked in Sprint 0).
- `block_id` is the block's 1-based position in `HI-Small_Patterns.txt`.
