"""Map bank labels to jurisdictions (PRD section 13).

Rule: an account's jurisdiction is the country of its bank.
- "<Label> Bank #N" gives that label's country.
- Any other name is a US-style name ("First Bank of Tampa"). Mapping these to
  the United States is INFERRED from currency evidence (81% of their payments are
  US dollars); the dataset authors do not document it.
- "Crytpo" (sic, as spelled in the data) banks have no national jurisdiction and
  use international virtual-asset guidance only.
"""

from __future__ import annotations

US_STYLE_LABEL = "US-style"
CRYPTO_LABEL = "Crytpo"

UNITED_STATES = "US"
INTERNATIONAL_VA = "INTL-VA"

LABEL_TO_JURISDICTION: dict[str, str] = {
    US_STYLE_LABEL: UNITED_STATES,
    CRYPTO_LABEL: INTERNATIONAL_VA,
    "Australia": "AU",
    "Austria": "AT",
    "Belgium": "BE",
    "Brazil": "BR",
    "Canada": "CA",
    "China": "CN",
    "Croatia": "HR",
    "Cyprus": "CY",
    "Estonia": "EE",
    "Finland": "FI",
    "France": "FR",
    "Germany": "DE",
    "Greece": "GR",
    "India": "IN",
    "Ireland": "IE",
    "Israel": "IL",
    "Italy": "IT",
    "Japan": "JP",
    "Latvia": "LV",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Malta": "MT",
    "Mexico": "MX",
    "Netherlands": "NL",
    "Portugal": "PT",
    "Russia": "RU",
    "Saudi Arabia": "SA",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Switzerland": "CH",
    "UK": "GB",
}


def jurisdiction_sql_case(label_column: str) -> str:
    """A SQL CASE expression mapping a label column to its jurisdiction code."""
    whens = " ".join(
        f"WHEN {label_column} = '{label}' THEN '{code}'"
        for label, code in LABEL_TO_JURISDICTION.items()
    )
    return f"CASE {whens} ELSE NULL END"
