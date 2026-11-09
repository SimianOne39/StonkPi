import math

# run this file from terminal to check configs
# "python config.py" when in server directory

# How many seconds between ticks. All values in this file are per tick.
# Small values run poorly, large values feel bad
TICK_SECONDS = 1.0 

#Don't touch, utility
TICKS_PER_HOUR = 3600 / TICK_SECONDS

# Stock categories. You probably shouldn't change this unless you know what you're doing.
CATEGORIES = ("safe", "medium", "risky")

# Spec range for each category stored as (min, max), change at your own risk.
# count         -> How many stocks are produced from this category. Large values run slow.
# start_price   -> Controls price stock starts at and baseline price
# volatility    -> The biggest controller of the price change per tick,
#                  higher means larger spikes in both directions
# drift         -> Rate at which the price will drift. Can be positive or negative
# reversion     -> How strong the pull back to baseline is
# jump_prob     -> Controls the probability of large jumps, in both directions
# jump_scale    -> Controls the size of large jumps
# death_prob    -> Controls the chance of a stock to "die", dropping to 0 and
#                  rerolling all stats
CATEGORY_SPECS = {
    "safe": {
        "count": 18,
        "start_price": (20.0, 300.0),
        "volatility":  (0.0005, 0.002),
        "drift":       (0.00001, 0.00004),
        "reversion":   (0.0005, 0.003),     # half-life roughly 4 to 23 minutes
        "jump_prob":   (0.0, 0.0001),       # one jump every 2.8 to inf hours
        "jump_scale":  (0.01, 0.02),
        "death_prob":  (0.0, 0.0000009)
    },
    "medium": {
        "count": 18,
        "start_price": (5.0, 150.0),
        "volatility":  (0.002, 0.006),
        "drift":       (-0.00001, 0.00005),
        "reversion":   (0.0002, 0.001),     # half-life roughly 12 to 58 minutes
        "jump_prob":   (0.0002, 0.0005),    # one jump every ~33 to 83 minutes
        "jump_scale":  (0.02, 0.04),
        "death_prob":  (0.000001, 0.000005),
    },
    "risky": {
        "count": 18,
        "start_price": (3.0, 60.0),
        "volatility":  (0.006, 0.016),
        "drift":       (-0.00003, 0.0001),
        "reversion":   (0.0001, 0.0005),    # half-life roughly 23 minutes to 2 hours
        "jump_prob":   (0.0005, 0.002),     # one jump every ~8 to 33 minutes
        "jump_scale":  (0.05, 0.15),
        "death_prob":  (0.00001, 0.00005),
    }
}

# Amount of ticks dead stocks wait before rerolling into a new stock
DELIST_DELAY = 10 

# How many dead stock's names are reserved
NUM_RETIRED_NAMES = 100 

# If stock price is below this value the stock dies
MIN_PRICE = 0.01

# If stock price drops below this value multiplied by the stock's baseline, the stock dies
COLLAPSE_FRACTION = 0.001

# Stock price can't go above this value times the baseline
STOCK_CAP_MULT = 10


# Checks every setting above. Call at startup (harness, server).
# Keys every category spec must contain as (min, max) ranges. These must match
# the StockParams fields plus start_price. Add "beta" here when it exists.
RANGE_KEYS = ("start_price", "volatility", "drift", "reversion",
              "jump_prob", "jump_scale", "death_prob")

# Possible 3-letter names (26 letters, 3 positions)
NAME_SPACE = 26 ** 3


def _is_number(x):
    """True for real, finite numbers (bools don't count)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _check_range(errors, where, key, rng):
    """Check one (min, max) range and add any problems to errors."""
    if not isinstance(rng, (tuple, list)) or len(rng) != 2 or not all(_is_number(v) for v in rng):
        errors.append(f"{where} must be a (min, max) pair of finite numbers, got {rng!r}")
        return
    lo, hi = rng
    if lo > hi:
        errors.append(f"{where}: min {lo} is greater than max {hi}")

    if key == "start_price":
        if lo <= 0:
            errors.append(f"{where}: min must be > 0, got {lo}")
        elif _is_number(MIN_PRICE) and lo <= MIN_PRICE:
            errors.append(f"{where}: min {lo} must be above MIN_PRICE ({MIN_PRICE}), "
                          f"or stocks could be created already dead")
    elif key in ("reversion", "jump_prob", "death_prob"):
        if lo < 0 or hi > 1:
            errors.append(f"{where}: values must stay between 0 and 1, got ({lo}, {hi})")
    elif key in ("volatility", "jump_scale"):
        if lo < 0:
            errors.append(f"{where}: min must be >= 0, got {lo}")
    # drift can be negative or positive, so it has no bounds


def validate_config(specs=None, categories=None):
    """Check the whole config. Raises ValueError listing every problem found.

    specs and categories default to the module-level settings; pass copies
    to test variations without editing the real values.
    """
    specs = CATEGORY_SPECS if specs is None else specs
    categories = CATEGORIES if categories is None else categories
    errors = []

    # ---- single-value settings ----
    if not _is_number(TICK_SECONDS) or TICK_SECONDS <= 0:
        errors.append(f"TICK_SECONDS must be a number > 0, got {TICK_SECONDS!r}")
    for name, value in (("DELIST_DELAY", DELIST_DELAY),
                        ("NUM_RETIRED_NAMES", NUM_RETIRED_NAMES)):
        if not _is_int(value) or value < 0:
            errors.append(f"{name} must be an integer >= 0, got {value!r}")
    if not _is_number(MIN_PRICE) or MIN_PRICE <= 0:
        errors.append(f"MIN_PRICE must be a number > 0, got {MIN_PRICE!r}")
    if not _is_number(COLLAPSE_FRACTION) or not 0 < COLLAPSE_FRACTION < 1:
        errors.append(f"COLLAPSE_FRACTION must be between 0 and 1, got {COLLAPSE_FRACTION!r}")

    # ---- category names ----
    if (not isinstance(categories, (tuple, list)) or len(categories) == 0
            or not all(isinstance(c, str) and c and c == c.lower() for c in categories)
            or len(set(categories)) != len(categories)):
        errors.append(f"CATEGORIES must be a non-empty tuple of unique lowercase strings, "
                      f"got {categories!r}")
        categories = []
    if not isinstance(specs, dict):
        errors.append(f"CATEGORY_SPECS must be a dictionary, got {type(specs).__name__}")
        specs = {}
    missing = sorted(set(categories) - set(specs))
    extra = sorted(set(specs) - set(categories))
    if missing:
        errors.append(f"CATEGORY_SPECS has no entry for: {', '.join(missing)}")
    if extra:
        errors.append(f"CATEGORY_SPECS has entries not listed in CATEGORIES: {', '.join(extra)}")

    # ---- each category spec ----
    total_stocks = 0
    allowed_keys = set(RANGE_KEYS) | {"count"}
    for cat in categories:
        spec = specs.get(cat)
        if spec is None:
            continue  # already reported as missing
        where = f"CATEGORY_SPECS[{cat!r}]"
        if not isinstance(spec, dict):
            errors.append(f"{where} must be a dictionary, got {type(spec).__name__}")
            continue

        count = spec.get("count")
        if not _is_int(count) or count <= 0:
            errors.append(f"{where}['count'] must be an integer > 0, got {count!r}")
        else:
            total_stocks += count

        for key in RANGE_KEYS:
            if key not in spec:
                errors.append(f"{where} is missing the {key!r} range")
            else:
                _check_range(errors, f"{where}[{key!r}]", key, spec[key])
        for key in sorted(set(spec) - allowed_keys):
            errors.append(f"{where} has unknown key {key!r} (typo?)")

    # ---- name pool must have room ----
    if _is_int(NUM_RETIRED_NAMES) and total_stocks + NUM_RETIRED_NAMES > NAME_SPACE // 2:
        errors.append(f"{total_stocks} stocks plus {NUM_RETIRED_NAMES} retired names is more than "
                      f"half of the {NAME_SPACE} possible names; picking a free name would get slow")

    if errors:
        raise ValueError("Invalid config:\n  " + "\n  ".join(errors))


if __name__ == "__main__":
    validate_config()
    print("config OK")


# Blocklist... it has to be done somewhere
# Credit to ElementalEngine2 for most of this list, you made my life easier
BLOCKED = ["ANL", "ANS", "ASS", "AZN", "BBW", "BCH", "CAC", "CAK", 
                    "CAQ", "CLT", "CNC", "CNT", "COC", "COK", "COQ", "COX", 
                    "CPD", "CUM", "DCK", "DIC", "DIK", "DIQ", "DIX", "DMN", 
                    "DSH", "DYC", "DYK", "DYQ", "EYP", "FAG", "FAP", "FCK", 
                    "FCU", "FGT", "FKU", "FML", "FOB", "FQU", "FUC", "FUK", 
                    "FUQ", "FUX", "GAI", "GAY", "GEI", "GEY", "GIZ", "GUC", 
                    "GUK", "GUQ", "GVR", "GZZ", "HOE", "HOR", "IRA", "JAP", 
                    "JEW", "JIZ", "JOO", "JYZ", "JZZ", "KAC", "KAK", "KAQ", 
                    "KIK", "KKK", "KLT", "KNT", "KOC", "KOK", "KOQ", "KOX", 
                    "KUM", "KYC", "KYK", "KYQ", "KYS", "LCK", "LIC", "LIK", 
                    "LIQ", "LOL", "LSD", "MFF", "MIC", "MIK", "MIQ", "MLF", 
                    "MUF", "MYC", "MYK", "MYQ", "NAD", "NDS", "NDZ", "NEG", 
                    "NGR", "NIG", "NIP", "NOG", "NUT", "ORL", "PCP", "PEE", 
                    "PEG", "PHC", "PHK", "PHQ", "PIS", "PMS", "PNS", "POO", 
                    "POT", "PRC", "PRK", "PRN", "PRQ", "PSS", "PSY", "PUS", 
                    "RAC", "RAK", "RAQ", "RCK", "SAC", "SAK", "SAQ", "SCK", 
                    "SEX", "SFU", "SHT", "SJV", "SLT", "SNM", "SOB", "SOL", 
                    "STD", "SUC", "SUK", "SUQ", "SXE", "SXI", "SXX", "SXY", 
                    "SYD", "THC", "TIT", "TOC", "TOK", "TOQ", "TWT", "VAG", 
                    "VAJ", "VGN", "VJN", "WAC", "WAK", "WAQ", "WCK", "WOP", 
                    "WTF", "XTC", "XXX"]