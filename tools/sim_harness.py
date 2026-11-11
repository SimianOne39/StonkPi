import itertools
import json
import os
import random
import re
import string
from collections import deque
from contextlib import contextmanager

import matplotlib.pyplot as plt

from server import config
from server.names import NamePool
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



# ---------------------------------------------------------------------------
# NamePool tests
# ---------------------------------------------------------------------------

ALL_NAMES = ["".join(t) for t in itertools.product(string.ascii_uppercase, repeat=3)]
TOTAL_STOCKS = sum(spec["count"] for spec in config.CATEGORY_SPECS.values())
NAME_FORMAT = re.compile(r"^[A-Z]{3}$")


@contextmanager
def patched_config(**overrides):
    """Temporarily change config values; restored even if the test fails."""
    missing = object()
    saved = {key: getattr(config, key, missing) for key in overrides}
    try:
        for key, value in overrides.items():
            setattr(config, key, value)
        yield
    finally:
        for key, value in saved.items():
            if value is missing:
                delattr(config, key)
            else:
                setattr(config, key, value)


def fill_pool(pool, count):
    """Pick count names, like creating the starting market."""
    return [pool.pick() for _ in range(count)]


def churn(pool, chooser, cycles):
    """Retire a random active name and pick a replacement, cycles times.

    chooser is a random.Random, so two pools can be given identical choices.
    Returns the list of newly picked names.
    """
    picks = []
    for _ in range(cycles):
        victim = chooser.choice(sorted(pool.active))
        pool.retire(victim)
        picks.append(pool.pick())
    return picks


def assert_raises(exc_type, fn, *args):
    try:
        fn(*args)
    except exc_type:
        return
    raise AssertionError(f"{fn.__name__}{args} should have raised {exc_type.__name__}")


def test_names_blocklist_defined():
    assert hasattr(config, "BLOCKED"), "config.BLOCKED is missing (names.py reads it)"


def test_names_unique_under_churn():
    pool = NamePool(1)
    fill_pool(pool, TOTAL_STOCKS)
    chooser = random.Random(2)
    for cycle in range(3000):
        churn(pool, chooser, 1)
        # A duplicate pick would collapse into the set and shrink the count.
        assert len(pool.active) == TOTAL_STOCKS, (
            f"active names changed to {len(pool.active)} at cycle {cycle}")
    bad = [n for n in pool.active if not NAME_FORMAT.match(n)]
    assert not bad, f"names that are not three uppercase letters: {bad[:5]}"


def test_names_retired_stay_out_then_return():
    # Shrink the name space to 1000 names and the cooldown to 50 retirements,
    # so a name can realistically come back within one test run.
    allowed = set(ALL_NAMES[:1000])
    with patched_config(BLOCKED=frozenset(ALL_NAMES) - allowed, NUM_RETIRED_NAMES=50):
        pool = NamePool(5)
        current = pool.pick()
        retired_order, picks = [], []
        for _ in range(20000):
            pool.retire(current)
            retired_order.append(current)
            current = pool.pick()
            assert current in allowed, f"{current} is outside the allowed names"
            # Compare against our own record of retirements, not the pool's,
            # so a pool that forgets to remember retired names can't pass.
            assert current not in retired_order[-50:], f"{current} was picked while on cooldown"
            assert current not in pool.retired, f"{current} was picked while on cooldown"
            picks.append(current)
    first = retired_order[0]
    assert first not in picks[:50], "first retired name came back too early"
    assert first in picks[50:], "first retired name never came back after its cooldown"


def test_names_blocklist_respected():
    blocked = frozenset(n for n in ALL_NAMES if n.startswith("A"))
    with patched_config(BLOCKED=blocked):
        pool = NamePool(6)
        current = pool.pick()
        for _ in range(20000):
            assert current not in blocked, f"blocked name {current} was picked"
            pool.retire(current)
            current = pool.pick()
        assert current not in blocked, f"blocked name {current} was picked"


def test_names_cover_alphabet():
    pool = NamePool(7)
    current = pool.pick()
    seen = [set(), set(), set()]
    for _ in range(5000):
        for pos in range(3):
            seen[pos].add(current[pos])
        pool.retire(current)
        current = pool.pick()
    for pos, letters in enumerate(seen):
        assert len(letters) == 26, f"position {pos} only ever used {len(letters)} letters"


def test_names_exhaustion():
    pool = NamePool(8)
    pool.active = set(ALL_NAMES)
    assert_raises(RuntimeError, pool.pick)


def test_names_retire_misuse():
    pool = NamePool(9)
    name = pool.pick()
    unknown = "QQQ" if name != "QQQ" else "WWW"
    assert_raises(ValueError, pool.retire, unknown)
    pool.retire(name)
    assert_raises(ValueError, pool.retire, name)


def test_names_save_restore():
    pool = NamePool(11)
    fill_pool(pool, TOTAL_STOCKS)
    churn(pool, random.Random(3), 500)

    # Round trip through real JSON text, like a real save
    saved = json.loads(json.dumps(pool.get_state()))
    restored = NamePool.from_state(saved)

    assert isinstance(restored.active, set), "active should be a set after restore"
    assert isinstance(restored.retired, deque), "retired should be a deque after restore"
    assert restored.retired.maxlen == config.NUM_RETIRED_NAMES, "retired lost its size limit"
    assert restored.active == pool.active, "active names were not restored"
    assert list(restored.retired) == list(pool.retired), "retired order was not restored"

    # Identical choices on both pools must give identical picks
    expected = churn(pool, random.Random(99), 500)
    actual = churn(restored, random.Random(99), 500)
    idx = first_difference(expected, actual)
    assert idx is None, (
        f"Restored pool diverged at pick {idx}: expected {expected[idx]!r}, got {actual[idx]!r}")
    assert (json.dumps(pool.get_state(), sort_keys=True)
            == json.dumps(restored.get_state(), sort_keys=True)), "final states differ"


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


def run_all_tests():
    """Run every test_ function, report failures, return True if all passed."""
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
        except Exception as e:
            failed.append(name)
            print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failed)} of {len(tests)} tests passed")
    return not failed


if __name__ == "__main__":
    if run_all_tests():
        demo_plot()
    else:
        raise SystemExit(1)
