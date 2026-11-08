import numpy as np

#Stock class for giving individual stocks personality
class Stock:
    def __init__(self, id, start_price, name, category, volatility, drift, reversion, jump_prob, jump_scale, death_prob, seed):
        self.id = id
        self.price = start_price
        self.baseline = start_price
        self.name = name
        self.volatility = volatility
        self.drift = drift
        self.reversion = reversion
        self.jump_prob = jump_prob
        self.jump_scale = jump_scale
        self.death_prob = death_prob
        self.rng = np.random.default_rng(seed)
        self.alive = True
        self.category = category

    #Updates the price of the stock
    def tick(self, market_mood=0):
        #handles dead stocks
        if self.alive == False:
            return None
        
        #randoms
        z = self.rng.standard_normal()
        u_jump = self.rng.random()
        j_size = self.rng.standard_normal()
        u_dead = self.rng.random()

        #new price components and calculation
        jump = self.jump_scale * j_size if u_jump < self.jump_prob else 0
        pull = self.reversion * (np.log(self.baseline) - np.log(self.price))
        log_change = self.drift - 0.5 * self.volatility**2 + pull + self.volatility * z + jump
        self.price *= np.exp(log_change)
        if u_dead < self.death_prob:
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
            "volatility": self.volatility,
            "drift": self.drift,
            "reversion": self.reversion,
            "jump_prob": self.jump_prob,
            "jump_scale": self.jump_scale,
            "death_prob": self.death_prob,
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
        self.volatility = state["volatility"]
        self.drift = state["drift"]
        self.reversion = state["reversion"]
        self.jump_prob = state["jump_prob"]
        self.jump_scale = state["jump_scale"]
        self.death_prob = state["death_prob"]
        self.price = state["price"]
        self.baseline = state["baseline"]
        self.alive = state["alive"]
        self.rng.bit_generator.state = state["rng"]
    
    #rebuilds stocks from save, stock does not have to exist
    @classmethod
    def from_state(cls, state):
        stock = cls(state["id"], state["price"], state["name"], state["category"], state["volatility"], state["drift"], state["reversion"], state["jump_prob"], state["jump_scale"], state["death_prob"], seed=0)
        stock.set_state(state)
        return stock
    

