import pandas as pd
from typing import Optional
from monitoring.logger import logger
from .base_client import BaseDataClient
from config.assets import get_asset_class, AssetClass
from .crypto_client import CryptoDataClient
from .stocks_client import StocksDataClient

def get_data_client(symbol: str) -> BaseDataClient:
    """Auto-detect client based on symbol metadata"""
    asset_class = get_asset_class(symbol)
    
    if asset_class == AssetClass.CRYPTO:
        return CryptoDataClient()
    elif asset_class in [AssetClass.STOCKS, AssetClass.FOREX, AssetClass.INDICES, AssetClass.COMMODITIES]:
        return StocksDataClient()
    
    return StocksDataClient() # Default fallback
