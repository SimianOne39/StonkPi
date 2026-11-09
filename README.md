# StonkPi

A multiplayer stock trading game that runs on a Raspberry Pi. The Pi hosts the market, and everyone else joins from their phone's browser over the same wifi. No app, no accounts, no internet needed.

Fifty-odd fake stocks rise and fall in real time. Everyone can buy and sell any of them at any moment, and whoever has the most money at the end wins. Fake money, fake companies, no financial advice.

## Status

Early development. The stock simulation and its configuration are working and tested. The web server, players, trading, and saving are not built yet, so there is nothing to play so far.

- [x] Per-stock price simulation (random walk with drift, mean reversion, jumps, and a chance to go bankrupt)
- [x] Seeded random numbers for every stock, with exact save and restore
- [x] Category settings with startup validation
- [x] Simulation harness with save/restore tests and plotting
- [ ] Name generator with a cooldown on recently retired names (in progress)
- [ ] Stock factory and rebirth of crashed stocks
- [ ] Market-wide mood that nudges all stocks together
- [ ] Players, trades, and a leaderboard
- [ ] Flask-SocketIO server and live charts in the browser
- [ ] Save and resume by username (SQLite)
- [ ] Host screen with a QR code to join

## How it's meant to work

The server is the only source of truth. Once per second it advances every stock, then pushes the new prices to every connected browser over WebSockets. Browsers just display things and send requests. A trade always executes at the server's current price, so a laggy phone can't buy at a stale one.

Each stock has its own personality, rolled when it's created:

- **Volatility:** how big its random moves are
- **Drift:** a slow upward or downward lean
- **Mean reversion:** how hard it gets pulled back toward its starting price
- **Jumps:** rare sudden moves, up or down
- **Death chance:** a small probability of crashing to zero

Stocks come in three categories, 18 of each by default:

| Category | What to expect |
|---|---|
| Safe | Barely moves, leans slightly upward, essentially never crashes |
| Medium | Swings of a few to a few dozen percent, with the occasional jump |
| Risky | Wild moves, big jumps, and a real chance of going to zero |

When a stock crashes, it waits a few seconds and comes back as a brand new stock in the same category, with a new three-letter name and freshly rolled stats. Anyone still holding the old one is out of luck.

## Getting started

You'll need Python 3.12 or newer. I'm developing on a Raspberry Pi 5, but nothing so far is Pi-specific. This is meant to be a lightweight game that you can run on anything!

```
git clone https://github.com/SimianOne39/StonkPi.git
cd StonkPi
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For the plotting and testing extras, install `requirements-dev.txt` instead.

Run everything from the project root, using `python -m`, so the imports resolve.

**Check the configuration**

```
python -m server.config
```

Prints `config OK`, or a list of everything wrong with the settings.

**Run the simulation harness**

```
python -m tools.sim_harness
```

This runs the save/restore tests and writes a chart comparing a Safe, Medium, and Risky stock over one simulated hour to `plots/volatility_comparison.png`.

## Tuning the market

Everything that shapes the market lives in `server/config.py`: how many stocks each category has, the range each stat is rolled from, how long a crashed stock waits before coming back, and so on. Every rate in the file is per tick, and the defaults assume one tick per second.

Stocks save their own stats, so editing the config only affects stocks created afterward. A saved game is never changed by it.

## Project layout

```
server/
  config.py        All tunable settings, plus validation
  stock.py         One stock: price movement, bankruptcy, save/restore
  names.py         Three-letter name pool (in progress)
  market.py        Market-wide mood (not started)
  game.py          The market and its rules (not started)
  players.py       Accounts, cash, holdings (not started)
  persistence.py   Saving and loading games (not started)
  app.py           Flask server and WebSocket events (not started)
templates/         login, player, and host pages
static/            Front-end JavaScript and CSS
tools/
  sim_harness.py   Tests and charts for the simulation
stonkPi.service    systemd unit for starting on boot
```

## A note on saving

A paused game should pick up exactly where it left off, which means the random number generators have to survive a restart too. Every stock saves the full internal state of its generator, and the harness checks that a restored stock produces the same prices, tick for tick, as one that never stopped.
