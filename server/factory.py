import math
from dataclasses import fields

from numpy.random import SeedSequence, default_rng

from server import config
from server.stock import Stock, StockParams
from server.names import NamePool

PARAM_KEYS = tuple(f.name for f in fields(StockParams))

def roll(rng, lo, hi):
    """One value from a (min, max) range."""
    
    if lo > 0:
        return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))
    else:
        return float(rng.uniform(lo, hi))

def check_specs(specs=None):
    """Raise ValueError if any category's range keys don't match StockParams."""
    specs = config.CATEGORY_SPECS if specs is None else specs
    expected = set(PARAM_KEYS) | {"start_price"}
    problems = []
    for category, spec in specs.items():
        found = set(spec) - {"count"}
        missing, unknown = sorted(expected - found), sorted(found - expected)
        if missing or unknown:
            problems.append(f"{category}: missing {missing}, unknown {unknown}")
        if problems:
            raise ValueError("Spec keys don't match StockParams:\n " + "\n ".join(problems))

