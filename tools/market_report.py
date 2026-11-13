import matplotlib.pyplot as plt
import random as ran
import os

from server import config
from server.factory import PARAM_KEYS, check_specs, make_stock, roll
from server.game import Game
from server.names import NamePool
from server.stock import Stock, StockParams


def plot_prices(series, labels=None, title="Price history",
                log_scale=False, filename=None):
    """Plot one or more price series.

    series:    list of price lists, one per stock or run
    labels:    optional list of legend labels, same length as series
    log_scale: use a log y axis (helpful when comparing very different prices)
    filename:  if given, save a PNG there instead of opening a window
    """
    fig, ax = plt.subplots(figsize=(10, 5))

    for i, prices in enumerate(series):
        label = labels[i] if labels else None
        ax.plot(prices, label=label, linewidth=1)

    ax.set_title(title)
    ax.set_xlabel("Tick")
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.3)
    if log_scale:
        ax.set_yscale("log")
    if labels:
        ax.legend()

    fig.tight_layout()
    if filename:
        folder = os.path.dirname(filename)
        if folder:
            os.makedirs(folder, exist_ok=True)
        fig.savefig(filename, dpi=120)
        plt.close(fig)
    else:
        plt.show()

    
def run_ticks(stock, n):
    """Advance a stock n ticks and return the list of prices."""
    return [stock.tick() for _ in range(n)]


def test_market():
    game = Game.new(ran.randint(0,999999))

    runs = []
    for slot in game.slots:
        runs.append(run_ticks(slot["stock"], 10800))
    plot_prices(runs, filename="plots/market_test.png")

if __name__ == "__main__":
    test_market()

