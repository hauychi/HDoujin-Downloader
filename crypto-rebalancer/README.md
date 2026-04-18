# crypto-rebalancer

Threshold-based portfolio rebalancing bot for Binance Spot.

Monitors a target allocation (e.g. BTC 50% / ETH 30% / SOL 20%) and places
market orders to restore the targets when any asset drifts more than a
configured percentage.

## Install

```bash
cd crypto-rebalancer
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configure

```bash
cp .env.example .env          # then fill in BINANCE_API_KEY / BINANCE_API_SECRET
cp portfolio.example.yaml portfolio.yaml
```

Edit `portfolio.yaml`:

| field                            | meaning                                                          |
|----------------------------------|------------------------------------------------------------------|
| `assets[].symbol` / `weight`     | target allocation; weights must sum to 1.0                       |
| `quote`                          | quote currency (USDT)                                            |
| `drift_threshold`                | rebalance when any `\|current - target\|` >= this (e.g. 0.05)    |
| `check_interval_seconds`         | how often the scheduler ticks                                    |
| `min_rebalance_interval_seconds` | minimum gap between successive rebalances                        |
| `max_trade_usdt`                 | hard cap on any single order's notional                          |
| `dry_run`                        | **true** = log-only (no orders). Flip to `false` to trade live.  |
| `use_testnet`                    | **true** = use `testnet.binance.vision`. Test here first.        |

## Usage

```bash
rebalancer balances             # print account balances + total USDT value
rebalancer check                # one drift report; never trades (forces dry_run)
rebalancer run                  # long-running loop (uses dry_run from config)
```

All commands accept `--config path/to/portfolio.yaml` (default: `./portfolio.yaml`).

## Go-live checklist

1. Generate **testnet** keys at <https://testnet.binance.vision> and write
   them to `.env`.
2. Set `use_testnet: true`, `dry_run: true` in `portfolio.yaml`.
3. `rebalancer balances` → confirms auth works.
4. `rebalancer check` → prints drift table, no orders.
5. Set `dry_run: false` (still on testnet). Start `rebalancer run` and
   deliberately skew holdings; confirm trades execute within `max_trade_usdt`.
6. Once satisfied: set `use_testnet: false` and a mainnet API key with
   **spot trading only, no withdrawals, IP-restricted**.
7. Run one more full cycle with `dry_run: true` on mainnet and review the
   log before finally flipping `dry_run: false`.

## Safety notes

- `.env` and `portfolio.yaml` are gitignored. Never commit keys.
- The bot uses plain market orders. There is no smart routing or slippage
  protection beyond `max_trade_usdt`.
- `rebalancer_state.json` tracks the last successful rebalance time and is
  consulted against `min_rebalance_interval_seconds` on every tick.
- There are no warranties. Use at your own risk.

## Tests

```bash
pytest
ruff check .
```
