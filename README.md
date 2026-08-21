# Health Factor Calculator (A2MCP Service)

A lightweight API that computes DeFi lending health factor, liquidation
price, and risk level for a collateral/debt position. Built for OKX.AI
as an Agent-to-MCP (A2MCP) service - no negotiation, callers hit the
endpoint and get a result back.

## What it does

Given a collateral position and a debt position, returns:

- **Health factor** (below 1 = liquidatable)
- **Liquidation price** (the collateral price at which HF hits 1)
- **Risk level**: Safe / Caution / Danger
- Which price source was used (live CoinGecko lookup, or a caller-supplied override)

## Run it locally

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Interactive API docs (auto-generated) at `http://localhost:8000/docs`.

## API

### `POST /health-factor`

**Request body:**

```json
{
  "collateral": {"asset": "ETH", "amount": 2},
  "debt": {"asset": "USDT", "amount": 3000},
  "collateral_price_usd": 3400,
  "debt_price_usd": 1,
  "liquidation_threshold": 0.825
}
```

`collateral_price_usd`, `debt_price_usd`, and `liquidation_threshold` are
all optional. If omitted, prices are fetched live from CoinGecko and the
threshold falls back to a built-in default for known assets (ETH, WETH,
BTC, WBTC, USDT, USDC, DAI).

**Response:**

```json
{
  "health_factor": 1.87,
  "collateral_value_usd": 6800.0,
  "debt_value_usd": 3000.0,
  "liquidation_price_usd": 1818.18,
  "liquidation_threshold_used": 0.825,
  "risk_level": "Safe",
  "collateral_price_source": "user-provided",
  "debt_price_source": "user-provided",
  "note": "Liquidation thresholds are approximate defaults unless overridden. Verify against live protocol parameters before relying on this for a real position."
}
```

### `GET /health`

Simple liveness check, returns `{"status": "ok"}`.

## Deploying (pick one — both have free tiers)

### Option A: Railway

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

Railway auto-detects the Python app from `requirements.txt` and gives you
a public URL.

### Option B: Render

1. Push this folder to a GitHub repo.
2. On render.com, create a new **Web Service**, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Either way, once deployed you'll have a public URL like
`https://your-service.up.railway.app/health-factor` — that's what you
register as your A2MCP endpoint on OKX.AI.

## Before registering on OKX.AI

- [ ] Confirm the deployed URL responds correctly (test with curl or `/docs`)
- [ ] Decide free vs. paid tier (free = no x402 integration needed, faster to ship)
- [ ] Double-check liquidation threshold defaults against current Aave v3
      parameters if you want to publicize this as trustworthy for real
      positions — the defaults here are reasonable approximations, not
      pulled from a live protocol feed
- [ ] Register as A2MCP per the OKX.AI tutorial, then submit for listing

## Known limitation

Live price lookups depend on CoinGecko's public API being reachable from
wherever you deploy. If you want to remove that dependency, you can swap
`fetch_price_usd()` in `main.py` for OKX's own price feed / OKLink API instead.
