# 0003 Bank jurisdiction rule

Status: accepted (Sprint 0), PRD section 13

Decision: a bank's jurisdiction comes from its name, mapped in `aml_agent/data/jurisdictions.py`.
- `<Label> Bank #N`: that label's country (ISO 3166 alpha-2, UK as GB). 32 country labels.
- `Crytpo` (sic): `INTL-VA`, international virtual-asset guidance only.
- Any other name (468 US-style names, 10,885 bank IDs): `US`. This is INFERRED from currency evidence (81% of payments sent are US dollars) and is not documented by the dataset authors.

An alert's jurisdiction is the seed account's bank jurisdiction. Most pattern blocks are cross-border, so this is a simplification to state in the README.
