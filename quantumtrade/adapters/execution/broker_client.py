from abc import ABC, abstractmethod
from typing import Dict, Any, List
from monitoring.logger import logger
from data.models import Trade
from datetime import datetime

class BaseBroker(ABC):
    @abstractmethod
    def place_order(self, symbol: str, side: str, quantity: float, price: float) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_balance(self) -> float:
        pass

class PaperBroker(BaseBroker):
    def __init__(self, initial_balance: float):
        self.balance = initial_balance
        self.positions: Dict[str, float] = {}
        self.trade_history: List[Trade] = []

    def place_order(self, symbol: str, side: str, quantity: float, price: float) -> Dict[str, Any]:
        cost = quantity * price
        
        if side == "BUY":
            if cost > self.balance:
                logger.error(f"Insufficient funds for BUY {symbol}")
                return {"status": "FAILED", "reason": "Insufficient funds"}
            
            self.balance -= cost
            self.positions[symbol] = self.positions.get(symbol, 0) + quantity
            trade = Trade(symbol=symbol, side="BUY", entry_price=price, quantity=quantity)
            self.trade_history.append(trade)
            logger.info(f"PAPER BUY: {quantity} {symbol} @ {price}")
            
        elif side == "SELL":
            current_pos = self.positions.get(symbol, 0)
            if current_pos < quantity:
                logger.error(f"Insufficient position for SELL {symbol}")
                return {"status": "FAILED", "reason": "Insufficient position"}
                
            self.balance += cost
            self.positions[symbol] -= quantity
            trade = Trade(symbol=symbol, side="SELL", entry_price=price, quantity=quantity)
            self.trade_history.append(trade)
            logger.info(f"PAPER SELL: {quantity} {symbol} @ {price}")
            
        return {"status": "SUCCESS", "price": price, "quantity": quantity}

    def get_balance(self) -> float:
        return self.balance
