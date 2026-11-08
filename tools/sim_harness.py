import numpy as np
import matplotlib.pyplot as plt
from server.stock import Stock
import json

def run_ticks(stock, n):
    """Advance a stock n ticks and return the list of prices."""
    return [stock.tick() for _ in range(n)]


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
        fig.savefig(filename, dpi=120)
        plt.close(fig)
    else:
        plt.show()

def first_difference(a, b):
    """Index of the first position where two lists differ, or None."""
    for i, (x,y) in enumerate(zip(a,b)):
        if x != y:
            return i
    return None

def test_save_restore(n=500, m=500):
    stock = Stock(1, 100.0, "ABC", 0.005, 0.00006, 0.0002, 123)
    run_ticks(stock, n)

    # Round trip through real JSON text
    saved = json.loads(json.dumps(stock.get_state()))

    # What we should expect without save
    expected = run_ticks(stock, m)

    # Rebuild from saved, then run m ticks
    restored = Stock.from_state(saved)
    actual = run_ticks(restored, m)

    idx = first_difference(expected, actual)
    assert idx is None, (
        f"Restored stock diverged at tick {idx}: "
        f"expected {expected[idx]!r}, got {actual[idx]!r}"
    )
    print("save/restore (alive stock): passed")

def test_save_restore_dead():
    stock = Stock(2, 50.0, "XYZ", 0.01, 0.00008, 0.0002, 456)
    run_ticks(stock, 100)
    stock.alive = False
    stock.price = 0.0

    saved = json.loads(json.dumps(stock.get_state()))
    restored = Stock.from_state(saved)

    assert restored.alive is False, "alive flag not restored"
    assert restored.name == stock.name, "name was not restored"
    assert restored.id == stock.id, "id was not restored"
    assert restored.price == stock.price, "price was not restored"
    print("save/restore (dead stock): passed")

def demo_plot():
    runs, labels = [], []
    for label, drift,vol in [("Safe 0.001",0.00008,0.001),
                                   ("Medium 0.004",0.00012,0.004),
                                   ("Risky 0.12",0.00016,0.012)]:
        stock = Stock(1, 100.0, "TST", vol, drift, 0.0002, 48328)
        runs.append(run_ticks(stock, 3600))
        labels.append(label)
    plot_prices(runs, labels, title="Volatility comparison, 1 hour",
                filename="plots/volatility_comparison.png")

if __name__ == "__main__":
    test_save_restore()
    test_save_restore_dead()
    demo_plot()
