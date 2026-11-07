import numpy as np

#control each individual stock
class Stock:
    def __init__(self, id, start_price, name, volatility, seed):
        self.id = id
        self.price = start_price
        self.name = name
        self.volatility = volatility
        self.rng = np.random.default_rng(seed)
        self.alive = True

    def tick(self):
        self.price *= np.exp((self.volatility * self.rng.standard_normal()) - 0.5 * self.volatility**2)
        return self.price
    
    def get_state(self):
        return {
            "version": 1,
            "id": self.id,
            "name": self.name,
            "volatility": self.volatility,
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
        self.price = state["price"]
        self.alive = state["alive"]
        self.rng.bit_generator.state = state["rng"]
    
    @classmethod
    def from_state(cls, state):
        stock = cls(state["id"], state["price"], state["name"], state["volatility"], seed=0)
        stock.set_state(state)
        return stock
    

