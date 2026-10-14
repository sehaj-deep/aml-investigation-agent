"""Golden numbers, copied from docs/PRD.md Appendix A and the Sprint 0 Verify list.

Never edit a value here to make a test pass. A mismatch is a finding: stop and
report it.
"""

from datetime import datetime

TRANSACTIONS = 5_078_345
LABELED = 5_177
ONE_IN = 981  # labeled rows are about 1 per 981

ACCOUNT_NUMBERS_UNIQUE = 518_573
ACCOUNT_NUMBERS_DUPLICATED = 8
TX_ACCOUNT_PAIRS = 515_088  # distinct (bank, account) pairs appearing in transactions

BANK_IDS = 30_470
BANKS_WITH_TWO_SPELLINGS = 58

FIRST_TS = datetime(2022, 9, 1, 0, 0)
LAST_TS = datetime(2022, 9, 18, 16, 18)
BACKGROUND_MIN_ROWS_PER_DAY_K = 207  # 09/01 to 09/10: 207K to 1.1M rows per day
BACKGROUND_MAX_ROWS_PER_DAY_M = 1.1
TAIL_ROWS = 1_108  # dated 09/11 to 09/18
TAIL_LABELED = 655
TAIL_UNLABELED = 453  # all ACH
TAIL_FIRST_DAY_ROWS = 396  # 09/11
TAIL_LAST_DAY_ROWS = 11  # 09/18

CUTOFF_60 = datetime(2022, 9, 6, 13, 36)
CUTOFF_80 = datetime(2022, 9, 8, 16, 12)

PAYMENT_FORMATS = {
    "Cheque": 1_864_331,
    "Credit Card": 1_323_324,
    "ACH": 600_797,
    "Reinvestment": 481_056,
    "Cash": 490_891,
    "Wire": 171_855,
    "Bitcoin": 146_091,
}
PATTERN_ROW_FORMATS = {"ACH": 3_208, "Bitcoin": 1}

TOP_CURRENCIES = {
    "US Dollar": 1_879_341,
    "Euro": 1_172_017,
    "Swiss Franc": 237_884,
    "Yuan": 206_551,
    "Shekel": 194_988,
    "Rupee": 192_065,
}

SELF_TRANSFERS = 591_212

PATTERN_BLOCKS = 370
PATTERN_BLOCKS_BY_TYPE = {
    "FAN-OUT": 48,
    "CYCLE": 54,
    "GATHER-SCATTER": 51,
    "STACK": 43,
    "RANDOM": 41,
    "BIPARTITE": 49,
    "FAN-IN": 40,
    "SCATTER-GATHER": 44,
}
PATTERN_ROWS = 3_209
SINGLE_ROW_BLOCKS = 43
SINGLE_ROW_BLOCKS_BY_TYPE = {"FAN-OUT": 8, "RANDOM": 13, "BIPARTITE": 18, "FAN-IN": 4}
MULTI_ROW_BLOCKS = 327
MULTI_ROW_BLOCKS_BY_TYPE = {
    "FAN-OUT": 40,
    "CYCLE": 54,
    "GATHER-SCATTER": 51,
    "STACK": 43,
    "RANDOM": 28,
    "BIPARTITE": 31,
    "FAN-IN": 36,
    "SCATTER-GATHER": 44,
}
BLOCK_SIZE_MIN = 1
BLOCK_SIZE_MAX = 32
BLOCK_SIZE_MEDIAN = 7
BLOCK_ACCOUNTS_MEDIAN = 8

PATTERN_ACCOUNTS = 3_170
PATTERN_ACCOUNTS_IN_MANY_BLOCKS = 100
MULTI_ROW_BLOCKS_SHARING_AN_ACCOUNT = 138
PATTERN_ROWS_SENDER_EARLIER_RECEIVED_LABELED = 1_395

SEED_ELIGIBLE_BLOCKS = 245
SEED_ELIGIBLE_BLOCKS_BY_TYPE = {
    "BIPARTITE": 28,
    "CYCLE": 40,
    "FAN-IN": 29,
    "FAN-OUT": 32,
    "GATHER-SCATTER": 33,
    "RANDOM": 24,
    "SCATTER-GATHER": 30,
    "STACK": 29,
}

OTHER_LAUNDERING = 1_968
OTHER_FIRST_DAY = datetime(2022, 9, 1)
OTHER_LAST_DAY = datetime(2022, 9, 10)
OTHER_TOUCHING_PATTERN_ACCOUNT = 42
OTHER_SENDER_EARLIER_RECEIVED_LABELED = 25
OTHER_GROUPS = 1_297
OTHER_ISOLATED = 1_238
OTHER_ISOLATED_BY_FORMAT = {"ACH": 1_187, "Bitcoin": 31, "Cheque": 20}
OTHER_LARGER_GROUPS = 59
OTHER_LARGEST_GROUP = {"rows": 247, "senders": 5, "receivers": 238}
OTHER_SECOND_GROUP = {"rows": 159, "senders": 2, "receivers": 156}

LABELED_ACH_AT_LEAST = 4_395

COUNTRY_LABELS = 33  # "<Label> Bank #N" labels, including "Crytpo"
US_STYLE_ACCOUNTS = 201_078
US_STYLE_NAMES = 468
US_STYLE_BANK_IDS = 10_885

# Share of payments sent, by sender bank label, rounded to a whole percent.
CURRENCY_SHARE_BY_LABEL = {
    "US-style": ("US Dollar", 81),
    "Canada": ("Canadian Dollar", 91),
    "UK": ("UK Pound", 88),
    "Germany": ("Euro", 98),
    "Switzerland": ("Swiss Franc", 96),
    "Japan": ("Yen", 85),
    "Crytpo": ("Bitcoin", 100),
}

BLOCKS_IN_ONE_COUNTRY = 39
BLOCKS_TOUCHING_CANADA = 58
