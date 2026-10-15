# Guidance sources

Public AML guidance used by the guidance lookup. All are works of the US federal government (FinCEN, FFIEC) and are in the public domain. The originals are downloaded by `scripts/build_guidance.py` into `data/guidance/raw` (not committed); `passages.jsonl` holds the extracted passages. Typography is normalized (whitespace, long dashes); the wording is unchanged.

| Document | Publisher | Original | Passages | SHA-256 (first 16) |
|---|---|---|---|---|
| FFIEC BSA/AML Examination Manual, Appendix F: Money Laundering and Terrorist Financing Red Flags | FFIEC | [ffiec_appendix_f.html](https://bsaaml.ffiec.gov/manual/Appendices/07) | 30 | `3ec6bf279def18ef` |
| FinCEN, Guidance on Preparing a Complete and Sufficient Suspicious Activity Report Narrative (2003) | FinCEN | [sarnarrcompletguidfinal_112003.pdf](https://www.fincen.gov/sites/default/files/shared/sarnarrcompletguidfinal_112003.pdf) | 73 | `937153099158eb92` |
| FinCEN, Suggestions for Addressing Common Errors Noted in Suspicious Activity Reporting (2007) | FinCEN | [SAR_Common_Errors_Web_Posting.pdf](https://www.fincen.gov/sites/default/files/shared/SAR_Common_Errors_Web_Posting.pdf) | 19 | `305e2710b30e405d` |
| FinCEN Advisory FIN-2014-A005, Update on U.S. Currency Restrictions in Mexico: Funnel Accounts and TBML (2014) | FinCEN | [FIN-2014-A005.pdf](https://www.fincen.gov/sites/default/files/shared/FIN-2014-A005.pdf) | 21 | `5d1902558bab8ebe` |
| FinCEN Guidance FIN-2006-G014, Potential Money Laundering Risks Related to Shell Companies (2006) | FinCEN | [AdvisoryOnShells_FINAL.pdf](https://www.fincen.gov/sites/default/files/shared/AdvisoryOnShells_FINAL.pdf) | 16 | `c88f49f7a27369b9` |
