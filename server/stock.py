import numpy as np
from dataclasses import dataclass, asdict, fields
from server import config

#parameters for stock creation
@dataclass(frozen=True)
class StockParams:
    """Fixed personality of one stock. Never changes during its life."""
    volatility: float
    drift: float = 0.0
    reversion: float = 0.0
    jump_prob: float = 0.0
    jump_scale: float = 0.0
    death_prob: float = 0.0

    def __post_init__(self):
        # Force plain Python floats so JSON saving never meets NumPy types.
        # (frozen=True blocks normal assignment, hence object.__setattr__.)
        for f in fields(self):
            object.__setattr__(self, f.name, float(getattr(self, f.name)))
        if self.volatility < 0:
            raise ValueError(f"volatility must be >= 0, got {self.volatility}")
        if self.jump_scale < 0:
            raise ValueError(f"jump_scale must be >= 0, got {self.jump_scale}")
        for name in ("reversion", "jump_prob", "death_prob"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1, got {value}")

#Stock class for giving individual stocks personality
class Stock:
    def __init__(self, id, start_price, name, category, params, seed):
        self.id = id
        self.price = start_price
        self.baseline = start_price
        self.name = name
        self.params = params
        self.rng = np.random.default_rng(seed)
        self.alive = True
        self.category = category

    #Updates the price of the stock
    def tick(self, market_mood=0):
        #handles dead stocks
        if self.alive == False:
            return self.price
        
        #randoms
        z = self.rng.standard_normal()
        u_jump = self.rng.random()
        j_size = self.rng.standard_normal()
        u_dead = self.rng.random()

        #new price components and calculation
        jump = self.params.jump_scale * j_size if u_jump < self.params.jump_prob else 0
        pull = self.params.reversion * (np.log(self.baseline) - np.log(self.price))
        log_change = self.params.drift - 0.5 * self.params.volatility**2 + pull + self.params.volatility * z + jump
        self.price *= np.exp(log_change)

        #infinite price handling and price cap
        if not np.isfinite(self.price) or self.price > (self.baseline * config.STOCK_CAP_MULT):
            self.price = self.baseline * 10

        if u_dead < self.params.death_prob or (self.price < (config.COLLAPSE_FRACTION * self.baseline) or self.price < config.MIN_PRICE):
            self.price = 0
            self.alive = False
        return self.price
    
    #save stock state for savegame
    def get_state(self):
        return {
            "version": 1,
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "params": asdict(self.params),
            "price": float(self.price),
            "baseline": self.baseline,
            "alive": self.alive,
            "rng": self.rng.bit_generator.state
        }
    
    #restore stock from savestate, stock has to exist
    def set_state(self, state):
        if state["version"] != 1:
            raise ValueError(f"Unknown stock state version: {state['version']}")
        self.id = state["id"]
        self.name = state["name"]
        self.category = state["category"]
        self.params = StockParams(**state["params"])
        self.price = state["price"]
        self.baseline = state["baseline"]
        self.alive = state["alive"]
        self.rng.bit_generator.state = state["rng"]

    def __repr__(self):
        status = f"{self.price:.2f}" if self.alive else "DEAD"
        return f"<Stock {self.id} {self.name} {self.category} {status}>"
    
    #rebuilds stocks from save, stock does not have to exist
    @classmethod
    def from_state(cls, state):
        stock = cls(state["id"], state["price"], state["name"], state["category"], StockParams(**state["params"]), seed=0)
        stock.set_state(state)
        return stock