import numpy as np
from server import config
from collections import deque
import string

LETTERS = string.ascii_uppercase

class NamePool:
    def __init__(self, seed):
        rng = np.random.default_rng(seed)
        active = set()
        retired = deque(maxlen=config.NUM_RETIRED_NAMES)

    def pick(self):
        n = int(self.rng.integers(26**3))
