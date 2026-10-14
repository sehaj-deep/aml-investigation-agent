# Sprint 0 Verify results

Run 2026-10-14 on the owner's machine (Windows 11, Docker Desktop WSL2, Python 3.12.9, DuckDB 1.5.6). Each item is from docs/sprints/sprint-0.md.

| Verify item | Result |
|---|---|
| Golden-number tests | All pass. Three PRD numbers were wording differences, not data problems; on 2026-10-14 the owner adopted the measured values: block-size median 6.5 (PRD 7), sender-earlier-received 1,406 (PRD 1,395), one-country blocks 41 (PRD 39). None is used by any logic |
| Two conversion runs give identical checksums | Yes: all 8 Parquet files byte-identical (second run into a separate folder, and again in the fresh clone) |
| Fresh clone starts the stack from scratch | Yes: clone, install with hashes, lint, 8 CI tests, conversion (checksums equal the original), alerts regenerate identically, 48 data tests pass + 3 xfail, Postgres healthy with pgvector 0.8.0 |
| Tool-query latency p95 in the real Docker setup | 222 ms from Parquet over the bind mount, 19 ms in memory (target under 1 s). Details: docs/decisions/0007 |
| Dev and eval sets share no pattern block | Yes (also no shared seed account) |
| Co-Authored-By commit rejected | Yes: `no-ai-coauthor` failed on `.git/COMMIT_EDITMSG:3`, exit code 1 |
| Commit of a file containing an em dash rejected | Yes: `no-em-dash` failed on `hook_test.md:1`, exit code 1 |
| Positive seeds: exactly one block, no other_laundering row | Yes, checked against the data for all 64 positives |
| Benign seeds: in no labeled row | Yes, all 64, each with at least one non-self transaction in its window |

Also checked: `tx_id` equals the raw CSV row number for the first, last and 1,000 random rows (streamed with the csv module); every one of the 3,209 pattern rows matches exactly one labeled transaction; the self-transfer count is 591,212 as in Appendix A.

Hook output (the em dash in test 2 is shown as [em dash] here):

```
no AI co-author or generator line in commit messages.......................Failed
- hook id: no-ai-coauthor
- exit code: 1
.git/COMMIT_EDITMSG:3:[test co-author trailer, redacted]

no em dashes anywhere....................................................Failed
- hook id: no-em-dash
- exit code: 1
hook_test.md:1:Hook test [em dash] should be rejected
```

Tagged v0.1.0.
