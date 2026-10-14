# 0002 Self-transfers: keep and flag

Status: accepted (Sprint 0)

Context: 591,212 rows (11.6%) send money from an account to itself, keyed by (integer bank ID, account). Every Reinvestment row (481,056) is one; only 11 are labeled laundering. They inflate counts and totals, make an account its own counterparty, and look like 1-hop cycles to a tracer.

Decision: keep every row and add the boolean column `is_self_transfer` to `transactions`. Benign-control activity matching excludes them. Whether graph tools hide them by default is decided in Sprint 1.

Why: nothing is lost, and the choice of what the agent sees stays explicit and testable.
