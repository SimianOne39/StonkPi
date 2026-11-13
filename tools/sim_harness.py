import copy
import itertools
import json
import math
import os
import random
import re
import string
from collections import deque
from contextlib import contextmanager

import matplotlib.pyplot as plt
from numpy.random import default_rng

from server import config
from server.factory import PARAM_KEYS, check_specs, make_stock, roll
from server.game import Game
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


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------

FACTORY_CATEGORIES = tuple(config.CATEGORY_SPECS)


def raised_message(exc_type, fn, *args, **kwargs):
    """Call fn, require it to raise exc_type, and return the message."""
    try:
        fn(*args, **kwargs)
    except exc_type as e:
        return str(e)
    raise AssertionError(f"{fn.__name__} should have raised {exc_type.__name__}")


def state_text(stock):
    """A stock's full saved state as comparable JSON text."""
    return json.dumps(stock.get_state(), sort_keys=True)


def single_value_specs(category="only", **overrides):
    """A specs dict whose ranges are all (x, x), so every roll is predictable."""
    spec = {
        "count": 1,
        "start_price": (50.0, 50.0),
        "volatility": (0.003, 0.003),
        "drift": (0.0, 0.0),
        "reversion": (0.0005, 0.0005),
        "jump_prob": (0.0002, 0.0002),
        "jump_scale": (0.03, 0.03),
        "death_prob": (0.000002, 0.000002),
    }
    spec.update(overrides)
    return {category: spec}


def assert_in_range(label, value, lo, hi):
    # Log-space rolling can land a hair outside the range through rounding.
    eps = 1e-12 * max(abs(lo), abs(hi))
    assert lo - eps <= value <= hi + eps, f"{label} = {value!r} is outside ({lo}, {hi})"


def assert_stock_matches_spec(stock, spec):
    assert_in_range("start_price", stock.baseline, *spec["start_price"])
    for key in PARAM_KEYS:
        assert_in_range(key, getattr(stock.params, key), *spec[key])


def build_market(master_seed=77):
    """Create the starting market the way the server would: one name per stock."""
    pool = NamePool(master_seed)
    market, uid = [], 0
    for category, spec in config.CATEGORY_SPECS.items():
        for _ in range(spec["count"]):
            market.append(make_stock(category, uid, master_seed, pool.pick()))
            uid += 1
    return pool, market


def test_factory_keys_match_config():
    # factory builds StockParams from PARAM_KEYS; config validates RANGE_KEYS.
    # If these drift apart, adding a stat in one place breaks the other.
    assert set(PARAM_KEYS) | {"start_price"} == set(config.RANGE_KEYS), (
        f"factory expects {sorted(set(PARAM_KEYS) | {'start_price'})}, "
        f"config.RANGE_KEYS is {sorted(config.RANGE_KEYS)}")
    assert len(set(PARAM_KEYS)) == len(PARAM_KEYS), "PARAM_KEYS has duplicates"


def test_factory_check_specs_accepts_real_config():
    before = copy.deepcopy(config.CATEGORY_SPECS)
    check_specs()
    check_specs(config.CATEGORY_SPECS)
    assert config.CATEGORY_SPECS == before, "check_specs modified the specs it was given"


def test_factory_check_specs_rejects_bad_keys():
    # count is not a StockParams field, so a spec without it is still fine
    no_count = copy.deepcopy(config.CATEGORY_SPECS)
    del no_count["safe"]["count"]
    check_specs(no_count)

    missing = copy.deepcopy(config.CATEGORY_SPECS)
    del missing["safe"]["drift"]
    msg = raised_message(ValueError, check_specs, missing)
    assert "safe" in msg and "drift" in msg, f"message doesn't name the problem: {msg!r}"

    no_price = copy.deepcopy(config.CATEGORY_SPECS)
    del no_price["medium"]["start_price"]
    msg = raised_message(ValueError, check_specs, no_price)
    assert "medium" in msg and "start_price" in msg, f"message doesn't name the problem: {msg!r}"

    typo = copy.deepcopy(config.CATEGORY_SPECS)
    typo["risky"]["volatilty"] = typo["risky"].pop("volatility")
    msg = raised_message(ValueError, check_specs, typo)
    assert "volatilty" in msg and "volatility" in msg, f"typo and missing key not reported: {msg!r}"


def test_factory_check_specs_reports_every_category():
    # The error says "Spec keys don't match" for the whole config, so one
    # run should list every broken category, not just the first one found.
    broken = copy.deepcopy(config.CATEGORY_SPECS)
    del broken["safe"]["drift"]
    del broken["risky"]["jump_scale"]
    msg = raised_message(ValueError, check_specs, broken)
    assert "safe" in msg, f"safe's problem missing from message: {msg!r}"
    assert "risky" in msg, f"risky's problem missing from message (stopped at first bad category?): {msg!r}"


def test_factory_check_specs_reads_config_by_default():
    broken = copy.deepcopy(config.CATEGORY_SPECS)
    del broken["medium"]["reversion"]
    with patched_config(CATEGORY_SPECS=broken):
        assert_raises(ValueError, check_specs)
    check_specs()  # real config is back and passes again


def test_factory_roll_range_and_type():
    rng = default_rng(1)
    ranges = [(1.0, 100.0), (0.0005, 0.002), (0.0, 0.0001),
              (-0.00001, 0.00005), (-1.0, 1.0), (5.0, 5.0), (0.0, 0.0)]
    for lo, hi in ranges:
        for _ in range(3000):
            v = roll(rng, lo, hi)
            # Plain float so JSON saving never meets NumPy types
            assert type(v) is float, f"roll returned {type(v).__name__} for ({lo}, {hi})"
            assert_in_range("roll", v, lo, hi)
        json.dumps(v)


def test_factory_roll_log_vs_linear():
    n = 20000
    # lo > 0: log-uniform, so the geometric middle is the median
    rng = default_rng(2)
    draws = [roll(rng, 1.0, 10000.0) for _ in range(n)]
    below = sum(v < 100.0 for v in draws) / n
    assert 0.47 < below < 0.53, f"positive range should be log-uniform; {below:.3f} fell below the geometric middle"

    # lo == 0: linear, so the plain middle is the median
    rng = default_rng(3)
    draws = [roll(rng, 0.0, 100.0) for _ in range(n)]
    below_mid = sum(v < 50.0 for v in draws) / n
    below_tenth = sum(v < 10.0 for v in draws) / n
    assert 0.47 < below_mid < 0.53, f"range starting at 0 should be linear; {below_mid:.3f} fell below the middle"
    assert 0.08 < below_tenth < 0.12, f"range starting at 0 should be linear; {below_tenth:.3f} fell below 10%"

    # negative lo: linear, and actually produces negatives (drift needs this)
    rng = default_rng(4)
    draws = [roll(rng, -1.0, 1.0) for _ in range(n)]
    negative = sum(v < 0 for v in draws) / n
    assert 0.47 < negative < 0.53, f"signed range should be linear; {negative:.3f} were negative"


def test_factory_roll_deterministic():
    a = [roll(default_rng(5), 1.0, 100.0) for _ in range(1)]
    b = [roll(default_rng(5), 1.0, 100.0) for _ in range(1)]
    assert a == b, "same generator seed gave different rolls"
    rng_a, rng_b = default_rng(6), default_rng(6)
    seq_a = [roll(rng_a, 0.0, 1.0) for _ in range(50)]
    seq_b = [roll(rng_b, 0.0, 1.0) for _ in range(50)]
    assert seq_a == seq_b, "same seed gave different roll sequences"
    assert seq_a != [roll(default_rng(7), 0.0, 1.0) for _ in range(50)], "different seeds gave the same rolls"


def test_factory_make_stock_basics():
    for i, category in enumerate(FACTORY_CATEGORIES):
        stock = make_stock(category, 10 + i, 2026, "ABC")
        assert isinstance(stock, Stock), f"{category}: not a Stock"
        assert stock.id == 10 + i, f"{category}: id not set"
        assert stock.name == "ABC", f"{category}: name not set"
        assert stock.category == category, f"{category}: category not set"
        assert stock.alive is True, f"{category}: stock was created dead"
        assert stock.price == stock.baseline, f"{category}: starts off its baseline"
        assert type(stock.price) is float, f"{category}: price is {type(stock.price).__name__}, not float"
        assert isinstance(stock.params, StockParams), f"{category}: params is not StockParams"
        assert stock.price > config.MIN_PRICE, f"{category}: starts below MIN_PRICE and would die on tick 1"
        assert_stock_matches_spec(stock, config.CATEGORY_SPECS[category])
    print("factory make_stock basics: passed")


def test_factory_unknown_category():
    assert_raises(ValueError, make_stock, "nope", 1, 1, "ABC")
    assert_raises(ValueError, make_stock, "Safe", 1, 1, "ABC")  # categories are lowercase
    # "safe" exists in config but not in these custom specs
    assert_raises(ValueError, make_stock, "safe", 1, 1, "ABC", single_value_specs())


def test_factory_deterministic():
    for category in FACTORY_CATEGORIES:
        a = make_stock(category, 3, 999, "ABC")
        b = make_stock(category, 3, 999, "ABC")
        assert a.params == b.params, f"{category}: same inputs gave different params"
        assert a.baseline == b.baseline, f"{category}: same inputs gave different start prices"
        assert state_text(a) == state_text(b), f"{category}: same inputs gave different starting state"
        idx = first_difference(run_ticks(a, 300), run_ticks(b, 300))
        assert idx is None, f"{category}: same inputs diverged at tick {idx}"


def test_factory_seed_sensitivity():
    base = make_stock("medium", 1, 2, "ABC")
    variants = {
        "different uid": make_stock("medium", 2, 2, "ABC"),
        "different master seed": make_stock("medium", 1, 3, "ABC"),
        # (seed, uid) swapped: a scheme like seed + uid would collide here
        "swapped seed and uid": make_stock("medium", 2, 1, "ABC"),
    }
    for label, other in variants.items():
        assert other.params != base.params, f"{label}: params were identical"
        assert other.baseline != base.baseline, f"{label}: start price was identical"
        assert (other.rng.bit_generator.state != base.rng.bit_generator.state), (
            f"{label}: tick random stream was identical")
    # zero is a legitimate seed and uid
    make_stock("safe", 0, 0, "ABC")


def test_factory_name_does_not_change_stock():
    a = make_stock("risky", 4, 11, "AAA")
    b = make_stock("risky", 4, 11, "ZZZ")
    assert a.name == "AAA" and b.name == "ZZZ", "name was not passed through"
    assert a.params == b.params and a.baseline == b.baseline, "name changed the rolled stats"
    assert a.rng.bit_generator.state == b.rng.bit_generator.state, "name changed the tick stream"


def test_factory_order_independent():
    # Making other stocks first (and ticking them) must not change stock 7.
    expected = state_text(make_stock("risky", 7, 31, "ABC"))
    for uid in range(50):
        other = make_stock(FACTORY_CATEGORIES[uid % len(FACTORY_CATEGORIES)], uid + 100, 31, "XYZ")
        run_ticks(other, 20)
    assert state_text(make_stock("risky", 7, 31, "ABC")) == expected, (
        "stock 7 changed after other stocks were made; there is hidden shared state")


def test_factory_tick_stream_independent_of_specs():
    # Retuning config should change the stats but not the underlying noise,
    # because ticks and rolls draw from separate child seeds.
    default = make_stock("safe", 5, 8, "ABC")
    tuned = make_stock("safe", 5, 8, "ABC", single_value_specs("safe"))
    assert default.params != tuned.params, "test setup: specs should give different params"
    assert default.rng.bit_generator.state == tuned.rng.bit_generator.state, (
        "tick random stream depends on the spec ranges")


def test_factory_custom_specs():
    specs = single_value_specs("only")
    before = copy.deepcopy(specs)
    stock = make_stock("only", 1, 1, "ABC", specs)
    assert specs == before, "make_stock modified the specs it was given"
    assert stock.category == "only"
    assert math.isclose(stock.baseline, 50.0, rel_tol=1e-9), f"start price {stock.baseline}"
    assert math.isclose(stock.params.volatility, 0.003, rel_tol=1e-9)
    assert stock.params.drift == 0.0
    assert math.isclose(stock.params.reversion, 0.0005, rel_tol=1e-9)
    assert math.isclose(stock.params.jump_prob, 0.0002, rel_tol=1e-9)
    assert math.isclose(stock.params.jump_scale, 0.03, rel_tol=1e-9)
    assert math.isclose(stock.params.death_prob, 0.000002, rel_tol=1e-9)

    # With no specs argument it should read config at call time
    with patched_config(CATEGORY_SPECS=single_value_specs("only")):
        stock = make_stock("only", 1, 1, "ABC")
        assert stock.category == "only"
        assert_raises(ValueError, make_stock, "safe", 1, 1, "ABC")
    make_stock("safe", 1, 1, "ABC")  # real config is back


def test_factory_missing_spec_key_fails_loudly():
    specs = single_value_specs("only")
    del specs["only"]["jump_scale"]
    assert_raises(KeyError, make_stock, "only", 1, 1, "ABC", specs)


def test_factory_rolled_params_always_valid():
    # StockParams rejects out-of-range values, so building many stocks from
    # the real config checks the config's ranges against those rules too.
    for category in FACTORY_CATEGORIES:
        spec = config.CATEGORY_SPECS[category]
        stocks = [make_stock(category, uid, 12345, "ABC") for uid in range(300)]
        for stock in stocks:
            assert stock.alive and stock.price > config.MIN_PRICE, f"{category} uid {stock.id} started dead"
            assert_stock_matches_spec(stock, spec)
        assert len({s.params for s in stocks}) == len(stocks), f"{category}: two stocks got identical params"
        assert len({s.baseline for s in stocks}) == len(stocks), f"{category}: two stocks got identical start prices"
        # Fresh stocks should be able to tick without blowing up
        for stock in stocks[:20]:
            prices = run_ticks(stock, 100)
            assert all(math.isfinite(p) for p in prices), f"{category} uid {stock.id} produced a non-finite price"


def test_factory_categories_are_ordered_by_risk():
    def median(values):
        values = sorted(values)
        return values[len(values) // 2]

    meds = {}
    for category in ("safe", "medium", "risky"):
        stocks = [make_stock(category, uid, 54321, "ABC") for uid in range(400)]
        meds[category] = {key: median([getattr(s.params, key) for s in stocks])
                          for key in ("volatility", "death_prob", "jump_scale")}
    for key in ("volatility", "death_prob", "jump_scale"):
        assert meds["safe"][key] < meds["medium"][key] < meds["risky"][key], (
            f"median {key} isn't safe < medium < risky: "
            f"{[meds[c][key] for c in ('safe', 'medium', 'risky')]}")


def test_factory_stock_save_restore():
    # A factory-built stock (seeded from a SeedSequence) must survive a real save.
    stock = make_stock("medium", 21, 2026, "SAV")
    run_ticks(stock, 300)
    assert stock.alive, "stock died during warm-up; pick another uid"

    saved = json.loads(json.dumps(stock.get_state()))
    expected = run_ticks(stock, 300)
    restored = Stock.from_state(saved)
    actual = run_ticks(restored, 300)

    idx = first_difference(expected, actual)
    assert idx is None, f"Restored factory stock diverged at tick {idx}: expected {expected[idx]!r}, got {actual[idx]!r}"
    assert_same_identity(restored, stock)


def test_factory_starting_market():
    pool, market = build_market()
    assert len(market) == TOTAL_STOCKS, f"expected {TOTAL_STOCKS} stocks, built {len(market)}"
    assert len({s.id for s in market}) == len(market), "duplicate stock ids"
    assert len({s.name for s in market}) == len(market), "duplicate stock names"
    assert {s.name for s in market} == pool.active, "pool's active names don't match the market"
    for category, spec in config.CATEGORY_SPECS.items():
        count = sum(s.category == category for s in market)
        assert count == spec["count"], f"{category}: expected {spec['count']} stocks, built {count}"
    assert all(s.alive for s in market), "a stock started dead"

    # Same seed, same market
    _, again = build_market()
    assert [state_text(s) for s in market] == [state_text(s) for s in again], "market isn't reproducible"
    # Different seed, different market
    _, other = build_market(master_seed=78)
    assert [s.params for s in market] != [s.params for s in other], "different master seed gave the same market"


def test_factory_replacement_after_death():
    # Dead stock is retired and replaced under a new uid and a new name.
    pool, market = build_market()
    victim = market[0]
    victim.alive, victim.price = False, 0.0
    next_uid = max(s.id for s in market) + 1

    pool.retire(victim.name)
    replacement = make_stock(victim.category, next_uid, 77, pool.pick())

    assert replacement.alive and replacement.price > config.MIN_PRICE, "replacement started dead"
    assert replacement.id != victim.id, "replacement reused the old id"
    assert replacement.name != victim.name, "replacement got the dead stock's name back"
    assert replacement.name not in {s.name for s in market[1:]}, "replacement stole a live stock's name"
    assert replacement.params != victim.params, "replacement is a clone of the dead stock"
    assert_stock_matches_spec(replacement, config.CATEGORY_SPECS[victim.category])


# ---------------------------------------------------------------------------
# Game tests
# ---------------------------------------------------------------------------

def churn_specs(per_category=4, death=(0.002, 0.01)):
    """Real specs, but a small market where stocks die often, so rebirths
    happen within a short test. Every stock starts at exactly $500, which
    lets tests tell whether the specs passed in were actually used."""
    specs = copy.deepcopy(config.CATEGORY_SPECS)
    for spec in specs.values():
        spec["count"] = per_category
        spec["death_prob"] = death
        spec["start_price"] = (500.0, 500.0)
    return specs


def game_state_text(game):
    """A game's full saved state as comparable JSON text."""
    return json.dumps(game.get_state(), sort_keys=True)


def slot_index_by_id(game):
    return {slot["stock"].id: i for i, slot in enumerate(game.slots)}


def test_game_new_basics():
    game = Game.new(77)
    stocks = [slot["stock"] for slot in game.slots]
    assert len(stocks) == TOTAL_STOCKS, f"expected {TOTAL_STOCKS} slots, got {len(stocks)}"

    expected = [c for c in config.CATEGORIES for _ in range(config.CATEGORY_SPECS[c]["count"])]
    assert [s.category for s in stocks] == expected, "slots are not in category order"
    assert [s.id for s in stocks] == list(range(1, TOTAL_STOCKS + 1)), "ids should run 1..N in slot order"
    assert game.next_uid == TOTAL_STOCKS + 1, f"next_uid is {game.next_uid}"
    assert game.tick_count == 0, "a new game should start at tick 0"
    assert all(s.alive for s in stocks), "a stock started dead"
    assert all(slot["countdown"] is None for slot in game.slots), "a new slot has a countdown"

    names = {s.name for s in stocks}
    assert len(names) == TOTAL_STOCKS, "duplicate names in the starting market"
    assert names == game.pool.active, "pool's active names don't match the market"

    assert game_state_text(Game.new(77)) == game_state_text(game), "same seed gave a different game"
    assert game_state_text(Game.new(78)) != game_state_text(game), "different seeds gave the same game"


def test_game_specs_honored():
    specs = churn_specs()
    for i, category in enumerate(config.CATEGORIES):
        specs[category]["count"] = i + 2          # 2, 3, 4, ...
    game = Game.new(5, specs)

    for i, category in enumerate(config.CATEGORIES):
        got = sum(slot["stock"].category == category for slot in game.slots)
        assert got == i + 2, f"{category}: expected {i + 2} stocks, got {got}"
    for slot in game.slots:
        assert_stock_matches_spec(slot["stock"], specs[slot["stock"].category])

    bad = copy.deepcopy(config.CATEGORY_SPECS)
    first = config.CATEGORIES[0]
    bad[first]["volatilty"] = bad[first].pop("volatility")
    msg = raised_message(ValueError, Game, 1, bad)
    assert "volatil" in msg, f"bad specs error doesn't name the key: {msg!r}"


def test_game_tick_empty_game():
    game = Game(1)
    assert game.tick() == [], "an empty game should produce no events"
    assert game.tick_count == 1, "tick_count should still advance"


def test_game_tick_without_deaths():
    specs = churn_specs(death=(0.0, 0.0))
    game = Game.new(3, specs)
    for _ in range(300):
        assert game.tick() == [], "events appeared although nothing can die"
    assert game.tick_count == 300, f"tick_count is {game.tick_count}"
    assert all(slot["stock"].alive for slot in game.slots), "a stock died with death_prob 0"
    assert any(slot["stock"].price != slot["stock"].baseline for slot in game.slots), "prices never moved"


def test_game_invariants_under_churn():
    game = Game.new(11, churn_specs())
    total = len(game.slots)
    categories = [slot["stock"].category for slot in game.slots]
    delay = config.DELIST_DELAY
    deaths = births = 0

    for _ in range(3000):
        events = game.tick()
        deaths += sum(e["type"] == "died" for e in events)
        births += sum(e["type"] == "born" for e in events)
        t = game.tick_count

        assert len(game.slots) == total, f"slot count changed to {len(game.slots)} at tick {t}"
        assert [sl["stock"].category for sl in game.slots] == categories, f"a slot changed category at tick {t}"
        stocks = [sl["stock"] for sl in game.slots]
        names = [s.name for s in stocks]
        assert len(set(names)) == total, f"duplicate names at tick {t}"
        assert set(names) == game.pool.active, f"names and pool disagree at tick {t}"
        assert len({s.id for s in stocks}) == total, f"duplicate ids at tick {t}"
        for slot in game.slots:
            stock, countdown = slot["stock"], slot["countdown"]
            if stock.alive:
                assert countdown is None, f"live stock {stock.name} has a countdown at tick {t}"
            else:
                assert countdown is not None and 1 <= countdown <= delay, (
                    f"dead stock {stock.name} has countdown {countdown} at tick {t}")

    assert deaths >= 30 and births >= 30, f"only {deaths} deaths and {births} births; test is too weak"
    assert game.next_uid == total + births + 1, "next_uid doesn't match the number of births"


def test_game_rebirth_timing():
    # A stock that dies on tick T is replaced on tick T + DELIST_DELAY.
    for delay in (1, 3, 10):
        specs = churn_specs()
        with patched_config(DELIST_DELAY=delay):
            game = Game.new(5, specs)
            died = {}                      # slot index -> (tick, id, name, category)
            deaths = births = 0
            for _ in range(2000):
                before = slot_index_by_id(game)
                events = game.tick()
                after = slot_index_by_id(game)
                t = game.tick_count
                for e in events:
                    if e["type"] == "died":
                        i = before[e["id"]]
                        assert i not in died, f"slot {i} died twice without a rebirth"
                        old = game.slots[i]["stock"]
                        died[i] = (t, old.id, old.name, old.category)
                        deaths += 1
                    else:
                        i = after[e["id"]]
                        assert i in died, f"slot {i} was reborn without dying"
                        t_died, old_id, old_name, old_category = died.pop(i)
                        assert t - t_died == delay, (
                            f"delay {delay}: slot {i} died at tick {t_died} but was reborn at tick {t}")
                        new = game.slots[i]["stock"]
                        assert new.alive and game.slots[i]["countdown"] is None, "replacement is not live"
                        assert new.id > old_id, "replacement should have a newer id"
                        assert new.name != old_name, "replacement kept the old name"
                        assert new.category == old_category, "replacement changed category"
                        assert old_name in game.pool.retired, "old name was not retired"
                        assert old_name not in game.pool.active, "old name is still active"
                        assert new.name in game.pool.active, "new name is not active"
                        assert_stock_matches_spec(new, specs[new.category])
                        births += 1
            assert deaths >= 20 and births >= 20, f"delay {delay}: only {deaths} deaths, {births} births"


def test_game_countdown_counts_down():
    with patched_config(DELIST_DELAY=5):
        game = Game.new(4, churn_specs())
        dead = {}                          # slot index -> (stock object, tick it died)
        checked = 0
        for _ in range(1500):
            game.tick()
            t = game.tick_count
            for i, slot in enumerate(game.slots):
                stock = slot["stock"]
                if stock.alive:
                    dead.pop(i, None)
                    continue
                if i not in dead:
                    dead[i] = (stock, t)
                original, t_died = dead[i]
                assert stock is original, f"slot {i} swapped its stock mid-countdown"
                assert stock.price == 0, f"dead stock {stock.name} has price {stock.price}"
                assert slot["countdown"] == 5 - (t - t_died), (
                    f"slot {i}: countdown is {slot['countdown']} at tick {t}, died at {t_died}")
                checked += 1
        assert checked > 50, "too few dead-stock ticks were checked"


def test_game_events_describe_what_happened():
    game = Game.new(8, churn_specs())
    seen = set()
    for _ in range(1000):
        events = game.tick()
        by_id = {slot["stock"].id: slot["stock"] for slot in game.slots}
        for e in events:
            assert set(e) == {"type", "id"}, f"unexpected event keys: {sorted(e)}"
            assert e["type"] in ("died", "born"), f"unknown event type {e['type']!r}"
            assert type(e["id"]) is int, f"event id {e['id']!r} is not an int"
            stock = by_id.get(e["id"])
            assert stock is not None, f"event refers to id {e['id']} which is in no slot"
            assert stock.alive == (e["type"] == "born"), f"{e['type']} event, but alive={stock.alive}"
            seen.add(e["type"])
    assert seen == {"died", "born"}, f"only saw event types {seen}"


def test_game_deterministic():
    specs = churn_specs()
    a, b = Game.new(21, specs), Game.new(21, specs)
    for t in range(1500):
        ea, eb = a.tick(), b.tick()
        assert ea == eb, f"same seed produced different events at tick {t + 1}"
    assert game_state_text(a) == game_state_text(b), "same seed ended in different states"

    c = Game.new(22, specs)
    for _ in range(1500):
        c.tick()
    assert game_state_text(c) != game_state_text(a), "different seeds ended in the same state"


def test_game_state_is_plain_json():
    game = Game.new(31, churn_specs())
    for _ in range(300):
        game.tick()
    state = game.get_state()
    assert json.loads(json.dumps(state)) == state, "state changes when sent through JSON"


def test_game_save_restore():
    specs = churn_specs()
    game = Game.new(41, specs)
    for _ in range(500):
        game.tick()
    # Make sure the save lands in the middle of a countdown
    for _ in range(1000):
        if any(slot["countdown"] is not None for slot in game.slots):
            break
        game.tick()
    assert any(slot["countdown"] is not None for slot in game.slots), "no stock was ever mid-countdown"
    assert any(slot["countdown"] is None for slot in game.slots), "every stock is dead; test is too weak"

    saved = json.loads(json.dumps(game.get_state()))        # real JSON text
    restored = Game.from_state(saved, specs)
    assert game_state_text(restored) == game_state_text(game), "state differs right after restore"

    for t in range(1500):
        ea, eb = game.tick(), restored.tick()
        assert ea == eb, f"restored game diverged at tick {t + 1}: {ea} vs {eb}"
    assert game_state_text(game) == game_state_text(restored), "final states differ"


def test_game_restore_keeps_saved_stock_params():
    # Saved stocks carry their own parameters; changing the specs on load
    # must only affect stocks created afterward.
    specs = churn_specs()
    game = Game.new(51, specs)
    for _ in range(200):
        game.tick()
    saved = json.loads(json.dumps(game.get_state()))

    other = copy.deepcopy(specs)
    for spec in other.values():
        spec["volatility"] = (0.01, 0.02)
        spec["start_price"] = (9.0, 9.0)
    restored = Game.from_state(saved, other)
    assert game_state_text(restored) == game_state_text(game), "restore changed saved stocks"


def test_game_set_state_validation():
    game = Game.new(61, churn_specs())
    for _ in range(50):
        game.tick()
    state = json.loads(json.dumps(game.get_state()))

    bad_version = copy.deepcopy(state)
    bad_version["version"] = 99
    assert_raises(ValueError, Game.from_state, bad_version)

    bad_names = copy.deepcopy(state)
    stock_state = bad_names["slots"][0]["stock"]
    stock_state["name"] = "QQQ" if stock_state["name"] != "QQQ" else "WWW"
    msg = raised_message(ValueError, Game.from_state, bad_names)
    assert "inconsistent" in msg, f"unhelpful error for an inconsistent save: {msg!r}"


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
