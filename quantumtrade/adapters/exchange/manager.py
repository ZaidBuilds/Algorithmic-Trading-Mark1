"""
Exchange connectivity manager for health checks and metadata.

Manages health checks for all connected exchanges and provides exchange metadata.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Any, Tuple
from enum import Enum
import logging

if TYPE_CHECKING:
    from quantumtrade.adapters.brokers.base import BaseBroker


class ExchangeStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"


@dataclass
class ExchangeMetadata:
    name: str
    symbols: List[str]
    fee_tier: float
    fee_maker: float
    fee_taker: float
    min_order_size: float
    max_order_size: float
    price_precision: int
    quantity_precision: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "symbols": self.symbols,
            "fee_tier": self.fee_tier,
            "fee_maker": self.fee_maker,
            "fee_taker": self.fee_taker,
            "min_order_size": self.min_order_size,
            "max_order_size": self.max_order_size,
            "price_precision": self.price_precision,
            "quantity_precision": self.quantity_precision,
        }


@dataclass
class HealthCheckResult:
    exchange_name: str
    status: ExchangeStatus
    latency_ms: Optional[float] = None
    last_check: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    weight: float = 1.0


class ExchangeConnectivityManager:
    def __init__(self, brokers: Dict[str, "BaseBroker"]):
        self.brokers = brokers
        self._metadata: Dict[str, ExchangeMetadata] = {}
        self._health_status: Dict[str, HealthCheckResult] = {}
        self._logger = logging.getLogger(__name__)
    
    def register_exchange(self, name: str, metadata: ExchangeMetadata) -> None:
        self._metadata[name] = metadata
    
    def check_health(self, exchange_name: Optional[str] = None) -> Dict[str, HealthCheckResult]:
        targets = [exchange_name] if exchange_name else list(self.brokers.keys())
        
        for name in targets:
            if name not in self.brokers:
                continue
            
            broker = self.brokers[name]
            result = self._check_broker_health(broker, name)
            self._health_status[name] = result
        
        return self._health_status
    
    def _check_broker_health(self, broker: "BaseBroker", name: str) -> HealthCheckResult:
        start_time = datetime.now()
        
        try:
            is_connected = broker.is_connected()
            latency_ms = None
            
            if is_connected:
                try:
                    balance = broker.get_account_balance()
                    end_time = datetime.now()
                    latency_ms = (end_time - start_time).total_seconds() * 1000
                    status = ExchangeStatus.CONNECTED
                except Exception as e:
                    status = ExchangeStatus.DEGRADED
                    self._logger.warning(f"Exchange {name} degraded: {e}")
            else:
                status = ExchangeStatus.DISCONNECTED
            
            return HealthCheckResult(
                exchange_name=name,
                status=status,
                latency_ms=latency_ms,
                weight=1.0 if status == ExchangeStatus.CONNECTED else 0.0,
            )
        except Exception as e:
            return HealthCheckResult(
                exchange_name=name,
                status=ExchangeStatus.DISCONNECTED,
                error_message=str(e),
            )
    
    def get_exchange_metadata(self, name: str) -> Optional[ExchangeMetadata]:
        return self._metadata.get(name)
    
    def get_all_symbols(self, exchange_name: Optional[str] = None) -> List[str]:
        if exchange_name:
            metadata = self._metadata.get(exchange_name)
            return metadata.symbols if metadata else []
        
        symbols: List[str] = []
        for metadata in self._metadata.values():
            symbols.extend(metadata.symbols)
        return list(set(symbols))
    
    def get_fee_tier(self, exchange_name: str) -> float:
        metadata = self._metadata.get(exchange_name)
        return metadata.fee_tier if metadata else 0.0
    
    def get_min_order(self, exchange_name: str) -> float:
        metadata = self._metadata.get(exchange_name)
        return metadata.min_order_size if metadata else 0.0
    
    def get_max_order(self, exchange_name: str) -> float:
        metadata = self._metadata.get(exchange_name)
        return metadata.max_order_size if metadata else float('inf')
    
    def rank_exchanges_for_symbol(
        self,
        symbol: str,
        execution_priority: str = "price",
    ) -> List[Tuple[str, float]]:
        scores: List[Tuple[str, float]] = []
        
        for name, broker in self.brokers.items():
            health = self._health_status.get(name)
            if not health or health.status != ExchangeStatus.CONNECTED:
                continue
            
            metadata = self._metadata.get(name)
            if not metadata or symbol not in metadata.symbols:
                continue
            
            score = self._calculate_exchange_score(name, broker, metadata, execution_priority)
            scores.append((name, score))
        
        return sorted(scores, key=lambda x: x[1], reverse=True)
    
    def _calculate_exchange_score(
        self,
        name: str,
        broker: "BaseBroker",
        metadata: ExchangeMetadata,
        priority: str,
    ) -> float:
        score = 0.0
        
        if priority == "price":
            score += (1 - metadata.fee_taker) * 0.4
            score += (1 - metadata.fee_maker) * 0.3
        elif priority == "speed":
            health = self._health_status.get(name)
            if health and health.latency_ms:
                score += (1 - min(health.latency_ms / 500, 1)) * 0.7
        
        score += 0.3 - (metadata.min_order_size / 1000) * 0.1
        score = max(0, min(1, score))
        
        return score
    
    def route_order(
        self,
        symbol: str,
        quantity: float,
        side: str,
        priority: str = "price",
    ) -> Optional[str]:
        ranked = self.rank_exchanges_for_symbol(symbol, priority)
        
        for name, score in ranked:
            metadata = self._metadata.get(name)
            health = self._health_status.get(name)
            
            if not metadata or not health:
                continue
            
            if health.status != ExchangeStatus.CONNECTED:
                continue
            
            if quantity >= metadata.min_order_size and quantity <= metadata.max_order_size:
                return name
        
        return ranked[0][0] if ranked else None
    
    def get_health_report(self) -> Dict[str, Any]:
        report = {
            "timestamp": datetime.now().isoformat(),
            "exchanges": [],
            "summary": {
                "total": len(self.brokers),
                "connected": 0,
                "degraded": 0,
                "disconnected": 0,
            },
        }
        
        for name, result in self._health_status.items():
            report["exchanges"].append({
                "name": name,
                "status": result.status,
                "latency_ms": result.latency_ms,
                "last_check": result.last_check.isoformat(),
            })
            
            if result.status == ExchangeStatus.CONNECTED:
                report["summary"]["connected"] += 1
            elif result.status == ExchangeStatus.DEGRADED:
                report["summary"]["degraded"] += 1
            else:
                report["summary"]["disconnected"] += 1
        
        return report