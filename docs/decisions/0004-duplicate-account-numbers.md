# 0004 The 8 duplicate account numbers

Status: investigated (Sprint 0)

Finding: the accounts file has 518,581 rows and 518,573 distinct account numbers. Eight account numbers each appear at two different banks, with different entity IDs, so they are different accounts:

| Account | Bank IDs | Bank names |
|---|---|---|
| 80FA55EF0, 80FA56340 | 138832, 13858 | Germany Bank #908, Italy Bank #97 |
| 80A7FD400, 80A7FDE00 | 27755, 28248 | Australia Bank #47, Australia Bank #44 |
| 81211BC00, 81211BA20 | 142574, 1490 | Germany Bank #945, Italy Bank #95 |
| 8135B8200, 8135B8250 | 221731, 27444 | National Bank of Danbury, Savings Bank of Fairfield |

Decision: no special handling. Accounts are keyed by (integer bank ID, account number), which is unique for all 518,581 rows (golden test `test_bank_account_pairs_are_unique`). Never key an account by its number alone.

Note: Appendix A's 201,078 US-style accounts counts distinct account numbers; the last pair above is US-style at both banks, so there are 201,080 US-style (bank, account) rows.
