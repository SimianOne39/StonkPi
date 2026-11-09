import numpy as np
from server import config
from collections import deque
import string

LETTERS = string.ascii_uppercase

class NamePool:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        self.active = set()
        self.retired = deque(maxlen=config.NUM_RETIRED_NAMES)

    def pick(self):
        count = 0
        while(count < 10000):
            n = int(self.rng.integers(26**3))
            a, rest = divmod(n, 26 * 26)
            b, c = divmod(rest, 26)
            name = string(LETTERS[a] + LETTERS[b] + LETTERS[c])
            if name not in self.active or self.retired or config.BLOCKED:
                self.active.append(name)
                return name
            count+=1
        raise RuntimeError("no free names, likely config issue")
    
    def retire(self, name):
        if name not in self.active:
            raise ValueError
        self.active.remove(name)
        self.retired.append(name)
        if len(self.retired) > config.NUM_RETIRED_NAMES:
            self.retired.popleft()

    def get_state(self):
        return{
            "version": 1,
            "rng": self.rng.bit_generator.state,
            "active": self.active.sort(),
            "retired": list(self.retired)
        }
    
    def set_state(self, state):
        self.rng.bit_generator.state = state["rng"]
        self.active = state["active"]
        self.retired = state["retired"]

    @classmethod
    def from_state(cls, state):
        namepool = cls(0)
        namepool.set_state(state)
        return namepool
        