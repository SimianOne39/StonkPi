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
    specs = config.CATEGORY_SPECS if specs is none else specs
    