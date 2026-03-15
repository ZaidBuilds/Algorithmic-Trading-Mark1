from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel

class AssetClass(str, Enum):
    CRYPTO = "CRYPTO"
    FOREX = "FOREX"
    STOCKS = "STOCKS"
    INDICES = "INDICES"
    COMMODITIES = "COMMODITIES"

class SymbolMetadata(BaseModel):
    name: str
    asset_class: AssetClass
    base_currency: str
    quote_currency: str
    min_lot_size: float = 0.0001
    tick_size: float = 0.01
    exchange: str = "DEFAULT"

# Asset Definitions
ASSETS_REGISTRY: Dict[AssetClass, List[str]] = {
    AssetClass.CRYPTO: ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
    AssetClass.FOREX: ["EURUSD=X", "GBPUSD=X", "USDJPY=X"],
    AssetClass.STOCKS: ["AAPL", "TSLA", "NVDA", "MSFT"],
    AssetClass.INDICES: ["^GSPC", "^IXIC", "^DJI"],
    AssetClass.COMMODITIES: ["GC=F", "CL=F"] # Gold, Crude Oil
}

def get_symbols_for_class(asset_class: AssetClass) -> List[str]:
    return ASSETS_REGISTRY.get(asset_class, [])

def get_asset_class(symbol: str) -> AssetClass:
    for ac, symbols in ASSETS_REGISTRY.items():
        if symbol in symbols:
            return ac
    return AssetClass.STOCKS # Default
