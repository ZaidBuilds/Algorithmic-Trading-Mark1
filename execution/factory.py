from config.assets import get_asset_class, AssetClass
from .crypto_broker import CryptoBrokerClient
from .forex_broker import ForexBrokerClient
from .stocks_broker import StocksBrokerClient
from .broker_client import BaseBroker

def get_broker_client(symbol: str, initial_balance: float) -> BaseBroker:
    """Factory to get the correct broker based on asset class"""
    asset_class = get_asset_class(symbol)
    
    if asset_class == AssetClass.CRYPTO:
        return CryptoBrokerClient(initial_balance)
    elif asset_class == AssetClass.FOREX:
        return ForexBrokerClient(initial_balance)
    else:
        return StocksBrokerClient(initial_balance)
