import json
import os

import matplotlib.pyplot as plt

from server.stock import Stock, StockParams


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
        folder = os.path.dirname(filename)
        if folder:
            os.makedirs(folder, exist_ok=True)
        fig.savefig(filename, dpi=120)
        plt.close(fig)
    else:
        plt.show()


def first_difference(a, b):
    """Index of the first position where two lists differ, or None."""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return None


def assert_same_identity(restored, original):
    """Check every non-RNG field survived the save/restore round trip."""
    assert restored.id == original.id, "id was not restored"
    assert restored.name == original.name, "name was not restored"
    assert restored.category == original.category, "category was not restored"
    assert restored.params == original.params, "params were not restored"
    assert restored.baseline == original.baseline, "baseline was not restored"
    assert restored.price == original.price, "price was not restored"
    assert restored.alive is original.alive, "alive flag was not restored"


def test_save_restore(n=500, m=500):
    params = StockParams(
        volatility=0.005,
        drift=0.00006,
        reversion=0.0002,
        jump_prob=0.0003,
        jump_scale=0.04,
        death_prob=0.0004,
    )
    stock = Stock(1, 100.0, "ABC", "test", params, 123)
    run_ticks(stock, n)

    # A stock that died during warm-up makes this test meaningless.
    assert stock.alive, "stock died during warm-up; pick another seed"

    # Round trip through real JSON text
    saved = json.loads(json.dumps(stock.get_state()))

    # What we should expect without a save
    expected = run_ticks(stock, m)

    # Rebuild from saved, then run m ticks
    restored = Stock.from_state(saved)
    actual = run_ticks(restored, m)

    idx = first_difference(expected, actual)
    assert idx is None, (
        f"Restored stock diverged at tick {idx}: "
        f"expected {expected[idx]!r}, got {actual[idx]!r}"
    )
    assert_same_identity(restored, stock)
    print("save/restore (alive stock): passed")


def test_save_restore_dead():
    params = StockParams(
        volatility=0.01,
        drift=0.00008,
        reversion=0.0002,
        jump_prob=0.0003,
        jump_scale=0.04,
        death_prob=0.0004,
    )
    stock = Stock(2, 50.0, "XYZ", "test", params, 456)
    run_ticks(stock, 100)
    stock.alive = False
    stock.price = 0.0

    saved = json.loads(json.dumps(stock.get_state()))
    restored = Stock.from_state(saved)

    assert_same_identity(restored, stock)
    print("save/restore (dead stock): passed")


def demo_plot():
    runs, labels = [], []
    # (label, volatility, drift, category)
    configs = [
        ("Safe 0.001", 0.001, 0.00008, "Safe"),
        ("Medium 0.004", 0.004, 0.00012, "Medium"),
        ("Risky 0.012", 0.012, 0.00016, "Risky"),
    ]
    for label, vol, drift, category in configs:
        # death_prob is 0 here so the chart shows volatility only
        params = StockParams(
            volatility=vol,
            drift=drift,
            reversion=0.0002,
            jump_prob=0.0003,
            jump_scale=0.04,
            death_prob=0.0,
        )
        stock = Stock(1, 100.0, "TST", category, params, 4832)
        runs.append(run_ticks(stock, 3600))
        labels.append(label)
    plot_prices(runs, labels, title="Volatility comparison, 1 hour",
                filename="plots/volatility_comparison.png")
    print("demo plot saved to plots/volatility_comparison.png")


if __name__ == "__main__":
    test_save_restore()
    test_save_restore_dead()
    demo_plot()
