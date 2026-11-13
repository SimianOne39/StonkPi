from numpy.random import SeedSequence
from server import config
from server.stock import Stock, StockParams
from server.names import NamePool
from server.factory import check_specs, make_stock

class Game:
    def __init__(self, master_seed, specs=None):
        self.master_seed = master_seed
        self.specs = config.CATEGORY_SPECS if specs is None else specs
        check_specs(self.specs)
        self.pool = NamePool(SeedSequence([master_seed, 0]))
        self.next_uid = 1
        self.tick_count = 0
        self.slots = []

    def _spawn(self, category):
        uid = self.next_uid
        self.next_uid += 1
        name = self.pool.pick()
        return make_stock(category, uid, self.master_seed, name, self.specs)

    @classmethod
    def new(cls, master_seed, specs=None):
        game = cls(master_seed, specs)
        for category in config.CATEGORIES:
            for _ in range(game.specs[category]["count"]):
                game.slots.append({"stock": game._spawn(category), "countdown": None})
        return game

    def tick(self):
        self.tick_count += 1
        events = []
        for slot in self.slots:
            stock = slot["stock"]
            if stock.alive:
                stock.tick()
                if not stock.alive:
                    slot["countdown"] = config.DELIST_DELAY
                    events.append({"type": "died", "id": stock.id})
            else:
                slot["countdown"] -= 1
                if slot["countdown"] <= 0:
                    self.pool.retire(stock.name)
                    new_stock = self._spawn(stock.category)
                    slot["stock"] = new_stock
                    slot["countdown"] = None
                    events.append({"type": "born", "id": new_stock.id})
        return events

    def get_state(self):
        return{
            "version": 1,
            "master_seed": self.master_seed,
            "next_uid": self.next_uid,
            "tick_count": self.tick_count,
            "pool": self.pool.get_state(),
            "slots": [{"stock": slot["stock"].get_state(),
                       "countdown": slot["countdown"]}
                       for slot in self.slots ]
        }
    
    def set_state(self, state):
        if not state["version"] == 1:
            raise ValueError(f"Unknown game state version: {state['version']}")
        self.master_seed = state["master_seed"]
        self.next_uid = state["next_uid"]
        self.tick_count = state["tick_count"]
        self.pool.set_state(state["pool"])
        self.slots = [{"stock": Stock.from_state(s["stock"]),
                       "countdown": s["countdown"]}
                       for s in state["slots"] ]
        names = {slot["stock"].name for slot in self.slots}
        if not names == self.pool.active: raise ValueError("save is inconsistent")

    @classmethod
    def from_state(cls, state, specs=None):
        game = cls(state["master_seed"], specs)
        game.set_state(state)
        return game
