from tracing.context import span, get_tracer, get_trace_id
from monitoring.tracing import get_tracer as get_global_tracer
import logging
from typing import Optional

# Get module-level tracer
tracer = get_global_tracer(__name__)
logger = logging.getLogger(__name__)


def trading_tick_span(symbols_processed: int = 0):
    """Create a span for the entire trading tick processing."""
    return span("trading_tick", symbols_processed=symbols_processed)


def data_fetch_span(symbol: str, success: bool = False, duration_ms: float = 0.0):
    """Create a span for data fetching operation."""
    return span(
        "data_fetch",
        symbol=symbol,
        success=success,
        duration_ms=duration_ms
    )


def signal_generation_span(symbol: str, strategy: str, signal_type: str, 
                          confidence: float, price: float):
    """Create a span for signal generation."""
    return span(
        "signal_generation",
        symbol=symbol,
        strategy=strategy,
        signal_type=signal_type,
        confidence=confidence,
        price=price
    )


def risk_check_span(symbol: str, quantity: float, price: float, 
                   portfolio_value: float, approved: bool):
    """Create a span for risk checking."""
    return span(
        "risk_check",
        symbol=symbol,
        quantity=quantity,
        price=price,
        portfolio_value=portfolio_value,
        approved=approved
    )


def order_execution_span(symbol: str, side: str, quantity: float, 
                        order_type: str, success: bool, 
                        order_id: Optional[str] = None,
                        error: Optional[str] = None):
    """Create a span for order execution."""
    attributes = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "success": success
    }
    if order_id:
        attributes["order_id"] = order_id
    if error:
        attributes["error"] = error
        
    return span("order_execution", **attributes)


def instrument_trading_engine_methods():
    """
    Instrument trading engine methods with tracing spans.
    This function patches the LiveTradingEngine class to add tracing.
    """
    try:
        from live.trading_engine import LiveTradingEngine
        
        # Store original methods
        original_trading_tick = LiveTradingEngine._trading_tick
        original_process_symbol = LiveTradingEngine._process_symbol
        original_fetch_data = LiveTradingEngine._fetch_data
        original_execute_signal_direct = LiveTradingEngine._execute_signal_direct
        
        # Patch _trading_tick
        def traced_trading_tick(self):
            with trading_tick_span(len(self.symbols)):
                return original_trading_tick(self)
        
        LiveTradingEngine._trading_tick = traced_trading_tick
        
        # Patch _process_symbol
        def traced_process_symbol(self, symbol: str):
            # Data fetch span
            start_time = time.perf_counter()
            data = self._fetch_data(symbol)
            fetch_duration = (time.perf_counter() - start_time) * 1000
            
            with data_fetch_span(
                symbol=symbol,
                success=data is not None and len(data) > 0,
                duration_ms=fetch_duration
            ):
                if data is None or len(data) < self.strategy.get_required_periods():
                    logger.warning(f"Insufficient data for {symbol}")
                    return
                
                # Calculate indicators (no span needed as it's fast)
                data = self.strategy.calculate_indicators(data)
                
                # Generate signal
                signal = self.strategy.generate_signal(data, len(data) - 1)
                
                with signal_generation_span(
                    symbol=symbol,
                    strategy=self.strategy.name,
                    signal_type=signal.signal_type,
                    confidence=signal.confidence,
                    price=signal.price
                ):
                    if signal.is_hold():
                        return
                    
                    # Event-driven path
                    if self.message_bus:
                        from quantumtrade.events import SignalEvent
                        signal_event = SignalEvent(
                            source="trading_engine",
                            symbol=symbol,
                            strategy=self.strategy.name,
                            signal_type=signal.signal_type,
                            confidence=signal.confidence,
                            price=signal.price,
                            metadata={
                                "timestamp": signal.timestamp.isoformat() if hasattr(signal, 'timestamp') else datetime.now().isoformat(),
                                "interval": self.interval,
                            },
                        )
                        self.message_bus.publish(signal_event)
                        logger.info(f"Published SignalEvent: {signal_event.signal_type} {symbol} @ ${signal.price:.2f}")
                    
                    # Legacy direct path
                    else:
                        self._execute_signal_direct(symbol, signal)
        
        LiveTradingEngine._process_symbol = traced_process_symbol
        
        logger.info("Trading engine methods instrumented with tracing")
        
    except Exception as e:
        logger.error(f"Failed to instrument trading engine: {e}")


# Import required modules for the instrumentation
import time
from datetime import datetime