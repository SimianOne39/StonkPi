import numpy as np

#control each individual stock
class Stock:
    def __init__(self, id, start_price, name, volatility, drift, reversion, seed):
        self.id = id
        self.price = start_price
        self.baseline = start_price
        self.name = name
        self.volatility = volatility
        self.drift = drift
        self.reversion = reversion
        self.rng = np.random.default_rng(seed)
        self.alive = True

    def tick(self):
        pull = self.reversion * (np.log(self.baseline) - np.log(self.price))
        log_change = self.drift - 0.5 * self.volatility**2 + pull + self.volatility * self.rng.standard_normal()
        self.price *= np.exp(log_change)
        return self.price
    
    def get_state(self):
        return {
            "version": 1,
            "id": self.id,
            "name": self.name,
            "volatility": self.volatility,
            "drift": self.drift,
            "reversion": self.reversion,
            "price": float(self.price),
            "baseline": self.baseline,
            "alive": self.alive,
            "rng": self.rng.bit_generator.state
        }
    
    def set_state(self, state):
        if state["version"] != 1:
            raise ValueError(f"Unknown stock state version: {state['version']}")
        self.id = state["id"]
        self.name = state["name"]
        self.volatility = state["volatility"]
        self.drift = state["drift"]
        self.reversion = state["reversion"]
        self.price = state["price"]
        self.baseline = state["baseline"]
        self.alive = state["alive"]
        self.rng.bit_generator.state = state["rng"]
    
    @classmethod
    def from_state(cls, state):
        stock = cls(state["id"], state["price"], state["name"], state["volatility"], state["drift"], state["reversion"], seed=0)
        stock.set_state(state)
        return stock
    

