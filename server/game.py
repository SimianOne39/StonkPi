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

    def new(self, master_seed, specs=None):
        game = cls(master_seed, specs)
        for category in config.CATEGORIES:
            for each in range(config.CATEGORY_SPECS[category])