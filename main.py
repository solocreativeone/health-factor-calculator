"""
Health Factor Calculator ASP (Agent-to-MCP service)

Given a collateral position and a debt position, returns the DeFi lending
health factor, the liquidation price, and a plain-language risk label.

Health Factor = (collateral_value_usd * liquidation_threshold) / debt_value_usd
Liquidation Price = debt_value_usd / (collateral_amount * liquidation_threshold)

HF > 1.5  -> Safe
HF 1.1-1.5 -> Caution
HF <= 1.1 -> Danger (near or at liquidation)

Prices are fetched live from CoinGecko's free public API unless the caller
supplies explicit override prices. Liquidation thresholds default to
approximate Aave v3 values for common assets, but callers can override
these too -- thresholds vary by protocol and change over time, so a caller
who needs precision should always confirm against the live protocol
parameters rather than trusting the defaults blindly.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import httpx

app = FastAPI(
    title="Health Factor Calculator",
    description="Computes DeFi lending health factor, liquidation price, and risk level. Registered on OKX.AI as an agent-to-agent (A2A) service.",
    version="1.0.0",
)

# Approximate Aave v3 liquidation thresholds for common assets.
# THESE ARE DEFAULTS ONLY -- verify against live protocol params for real positions.
DEFAULT_LIQUIDATION_THRESHOLDS = {
    "ETH": 0.825,
    "WETH": 0.825,
    "BTC": 0.80,
    "WBTC": 0.80,
    "USDT": 0.85,
    "USDC": 0.85,
    "DAI": 0.80,
}

# Symbol -> CoinGecko id, for live price lookups.
COINGECKO_IDS = {
    "ETH": "ethereum",
    "WETH": "weth",
    "BTC": "bitcoin",
    "WBTC": "wrapped-bitcoin",
    "USDT": "tether",
    "USDC": "usd-coin",
    "DAI": "dai",
    "OKB": "okb",
}


class Position(BaseModel):
    asset: str = Field(..., description="Asset symbol, e.g. 'ETH', 'USDT'")
    amount: float = Field(..., gt=0, description="Amount of the asset")


class HealthFactorRequest(BaseModel):
    collateral: Position
    debt: Position
    collateral_price_usd: Optional[float] = Field(
        None, description="Override live price for the collateral asset (USD)"
    )
    debt_price_usd: Optional[float] = Field(
        None, description="Override live price for the debt asset (USD)"
    )
    liquidation_threshold: Optional[float] = Field(
        None, gt=0, lt=1, description="Override liquidation threshold (0-1), e.g. 0.825"
    )


class HealthFactorResponse(BaseModel):
    health_factor: float
    collateral_value_usd: float
    debt_value_usd: float
    liquidation_price_usd: float
    liquidation_threshold_used: float
    risk_level: str
    collateral_price_source: str
    debt_price_source: str
    note: str


async def fetch_price_usd(symbol: str) -> float:
    cg_id = COINGECKO_IDS.get(symbol.upper())
    if not cg_id:
        raise HTTPException(
            status_code=400,
            detail=f"No live price source for '{symbol}'. Supply a price override instead.",
        )
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": cg_id, "vs_currencies": "usd"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    try:
        return float(data[cg_id]["usd"])
    except (KeyError, TypeError):
        raise HTTPException(status_code=502, detail=f"Price lookup failed for '{symbol}'.")


def risk_label(hf: float) -> str:
    if hf > 1.5:
        return "Safe"
    elif hf > 1.1:
        return "Caution"
    else:
        return "Danger"


@app.get("/")
async def root():
    return {
        "service": "Health Factor Calculator",
        "description": "POST /health-factor with a collateral and debt position to get "
        "the lending health factor, liquidation price, and risk level.",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/health-factor", response_model=HealthFactorResponse)
async def calculate_health_factor(req: HealthFactorRequest):
    collateral_symbol = req.collateral.asset.upper()
    debt_symbol = req.debt.asset.upper()

    # Resolve prices
    if req.collateral_price_usd is not None:
        collateral_price = req.collateral_price_usd
        collateral_price_source = "user-provided"
    else:
        collateral_price = await fetch_price_usd(collateral_symbol)
        collateral_price_source = "coingecko"

    if req.debt_price_usd is not None:
        debt_price = req.debt_price_usd
        debt_price_source = "user-provided"
    else:
        debt_price = await fetch_price_usd(debt_symbol)
        debt_price_source = "coingecko"

    # Resolve liquidation threshold
    if req.liquidation_threshold is not None:
        threshold = req.liquidation_threshold
    else:
        threshold = DEFAULT_LIQUIDATION_THRESHOLDS.get(collateral_symbol)
        if threshold is None:
            raise HTTPException(
                status_code=400,
                detail=f"No default liquidation threshold for '{collateral_symbol}'. "
                f"Supply 'liquidation_threshold' explicitly.",
            )

    collateral_value = req.collateral.amount * collateral_price
    debt_value = req.debt.amount * debt_price

    if debt_value == 0:
        raise HTTPException(status_code=400, detail="Debt value cannot be zero.")

    health_factor = (collateral_value * threshold) / debt_value
    liquidation_price = debt_value / (req.collateral.amount * threshold)

    return HealthFactorResponse(
        health_factor=round(health_factor, 4),
        collateral_value_usd=round(collateral_value, 2),
        debt_value_usd=round(debt_value, 2),
        liquidation_price_usd=round(liquidation_price, 2),
        liquidation_threshold_used=threshold,
        risk_level=risk_label(health_factor),
        collateral_price_source=collateral_price_source,
        debt_price_source=debt_price_source,
        note=(
            "Liquidation thresholds are approximate defaults unless overridden. "
            "Verify against live protocol parameters before relying on this for "
            "a real position."
        ),
    )