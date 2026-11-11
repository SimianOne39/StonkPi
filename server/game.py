from numpy.random import SeedSequence
from server import config
from server.stock import Stock, StockParams
from server.names import NamePool
import server.factory

class Game:
    def __init__(self, master_seed, specs=None):
        self.master_seed = master_seed
        self.specs = config.CATEGORY_SPECS if specs is None else specs
        server.factory.check_specs(self.specs)
        self.pool = NamePool(SeedSequence([master_seed, 0]))
        self.next_uid = 1
        self.tick_count = 0
        self.slots = []

    @classmethod
    def new(self, master_seed, specs=None):
        game = cls(master_seed, specs)
        for category in config.CATEGORIES:
            spec = config.CATEGORY_SPECS[category]
            count = spec["count"]
            for _ in range(count):
                name = self.pool.pick()
                uid = next_uid
                next_uid += 1
                stock = make_stock(category, uid, self.master_seed, name)
                slot = {stock, None}
                self.slots.append(slot)

    def tick(self):
        self.tick_count += 1
        events = []
        for slot in self.slots:
            stock, countdown = slot
            if stock.alive:
                stock.tick()
                if not stock.alive:
                    countdown = config.DELIST_DELAY
                    events.append({stock.id, "died"})
            else:
                countdown -= 1
                if countdown <= 0:
                    self.pool.retire(stock.name)
                    newStock = make_stock(stock.category, self.next_uid, self.master_seed, self.pool.pick())
                    self.next_uid += 1
                    slot = {newStock, None}
                    self.slots.append(slot)
                    events.append({newStock.id, "born"})
                    self.slots.remove(slot)
    return events
