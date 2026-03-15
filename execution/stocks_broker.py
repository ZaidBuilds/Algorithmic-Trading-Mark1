from typing import Dict, Any
from .broker_client import BaseBroker
from monitoring.logger import logger

class StocksBrokerClient(BaseBroker):
    def __init__(self, initial_balance: float):
        self.balance = initial_balance
        self.positions: Dict[str, float] = {}

    def place_order(self, symbol: str, side: str, quantity: float, price: float) -> Dict[str, Any]:
        cost = quantity * price
        if side.upper() == "BUY":
            if cost > self.balance:
                return {"status": "FAILED", "reason": "Insufficient Balance"}
            self.balance -= cost
            self.positions[symbol] = self.positions.get(symbol, 0) + quantity
        else:
            if self.positions.get(symbol, 0) < quantity:
                return {"status": "FAILED", "reason": "Insufficient Position"}
            self.balance += cost
            self.positions[symbol] -= quantity
            
        logger.info(f"STOCK {side}: {quantity} {symbol} @ {price}")
        return {"status": "SUCCESS"}

    def get_balance(self) -> float:
        return self.balance
