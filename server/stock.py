import numpy as np

#control each individual stock
class Stock:
    def __init__(self, id, start_price, name, volatility, drift, seed):
        self.id = id
        self.price = start_price
        self.name = name
        self.volatility = volatility
        self.drift = drift
        self.rng = np.random.default_rng(seed)
        self.alive = True

    def tick(self):
        log_change = self.drift - 0.5 * self.volatility**2 + self.volatility * self.rng.standard_normal()
        self.price *= np.exp(log_change)
        return self.price
    
    def get_state(self):
        return {
            "version": 1,
            "id": self.id,
            "name": self.name,
            "volatility": self.volatility,
            "drift": self.drift,
            "price": float(self.price),
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
        self.price = state["price"]
        self.alive = state["alive"]
        self.rng.bit_generator.state = state["rng"]
    
    @classmethod
    def from_state(cls, state):
        stock = cls(state["id"], state["price"], state["name"], state["volatility"], state["drift"], seed=0)
        stock.set_state(state)
        return stock
    

