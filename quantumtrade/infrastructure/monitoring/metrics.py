"""Central Prometheus metrics registry for QuantumTrade.

All metrics follow the naming convention: quantumtrade_<component>_<metric>
Labels are kept low-cardinality (<100 unique values per metric).

Usage:
    from monitoring.metrics import (
        TRADING_TICKS,
        ORDERS_SUBMITTED,
        track_latency,
    )

    # Increment counter
    TRADING_TICKS.labels(symbol="AAPL", outcome="success").inc()

    # Observe histogram
    with track_latency(ORDER_LATENCY, broker="alpaca", stage="execution"):
        result = broker.place_order(order)

    # Set gauge
    ACTIVE_POSITIONS.set(len(positions))

    # Access endpoint: http://localhost:8000/metrics
"""

import sys
import time
from functools import wraps
from typing import Callable, Optional

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    Enum,
    start_http_server,
    REGISTRY,
)

# ─────────────────────────────────────────
# Instrumentation Decorators
# ─────────────────────────────────────────

def track_latency(histogram: Histogram, **labels):
    """Decorator to automatically observe function duration in a histogram.

    Usage:
        @track_latency(ORDER_LATENCY, broker="alpaca", stage="execution")
        def place_order(order):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                histogram.labels(**labels).observe(duration)
        return wrapper
    return decorator


def count_calls(counter: Counter, **labels):
    """Decorator to automatically increment a counter on function call.

    Usage:
        @count_calls(FUNCTION_CALLS, name="process_tick")
        def process_tick():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            counter.labels(**labels).inc()
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ─────────────────────────────────────────
# System Metrics
# ─────────────────────────────────────────

# Python version info (info metric - static labels)
try:
    PYTHON_INFO = Info(
        'python_info',
        'Python runtime information'
    )
    PYTHON_INFO.info({
        'version': sys.version.replace('\n', ' ').replace('\r', ' '),
        'implementation': sys.implementation.name,
    })
except ValueError:
    # Already registered - get existing
    pass


PROCESS_CPU_SECONDS_TOTAL = Counter(
    'process_cpu_seconds_total',
    'Total CPU time spent in seconds',
)

PROCESS_VIRTUAL_MEMORY_BYTES = Gauge(
    'process_virtual_memory_bytes',
    'Virtual memory size in bytes',
)

# ─────────────────────────────────────────
# Trading Engine Metrics
# ─────────────────────────────────────────

TRADING_TICKS_TOTAL = Counter(
    'quantumtrade_trading_ticks_total',
    'Total number of trading ticks processed',
    ['symbol', 'outcome'],  # outcome: success, error, skipped
)

TRADING_TICK_DURATION_SECONDS = Histogram(
    'quantumtrade_trading_tick_duration_seconds',
    'Time spent processing a single trading tick',
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0],
)

ACTIVE_POSITIONS_COUNT = Gauge(
    'quantumtrade_active_positions_count',
    'Current number of open positions',
)

PORTFOLIO_VALUE_USD = Gauge(
    'quantumtrade_portfolio_value_usd',
    'Total portfolio value in USD',
)

CASH_BALANCE_USD = Gauge(
    'quantumtrade_cash_balance_usd',
    'Available cash balance in USD',
)

UNREALISED_PNL_USD = Gauge(
    'quantumtrade_unrealised_pnl_usd',
    'Unrealised profit/loss in USD',
)

REALISED_PNL_USD = Gauge(
    'quantumtrade_realised_pnl_usd',
    'Realised profit/loss in USD',
)

# ─────────────────────────────────────────
# Order Execution Metrics
# ─────────────────────────────────────────

ORDERS_SUBMITTED_TOTAL = Counter(
    'quantumtrade_orders_submitted_total',
    'Total orders submitted to broker',
    ['side', 'order_type', 'broker', 'status'],  # status: pending, filled, cancelled, rejected
)

ORDERS_FILLED_TOTAL = Counter(
    'quantumtrade_orders_filled_total',
    'Total orders successfully filled',
    ['side', 'broker'],
)

ORDER_LATENCY_SECONDS = Histogram(
    'quantumtrade_order_latency_seconds',
    'Order execution latency from submission to fill',
    ['broker', 'stage'],  # stage: signal_to_submit, submit_to_fill, total
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

SLIPPAGE_BASIS_POINTS = Gauge(
    'quantumtrade_slippage_basis_points',
    'Slippage vs mid-price in basis points (100 = 1%)',
    ['symbol', 'side'],
)

FILL_RATE = Gauge(
    'quantumtrade_fill_rate_percent',
    'Percentage of submitted orders that get filled',
    ['broker'],
)

# ─────────────────────────────────────────
# Execution Algorithm Metrics
# ─────────────────────────────────────────

ALGORITHM_ORDERS_TOTAL = Counter(
    'quantumtrade_algorithm_orders_total',
    'Total orders executed by algorithm',
    ['algorithm', 'side'],
)

EXECUTION_COST_BPS = Gauge(
    'quantumtrade_execution_cost_basis_points',
    'Total execution cost (explicit + implicit) in basis points',
    ['symbol', 'side', 'algorithm', 'broker'],
)

SLIPPAGE_BPS_EXEC = Gauge(
    'quantumtrade_slippage_basis_points_execution',
    'Slippage component of execution cost in basis points',
    ['symbol', 'side', 'algorithm'],
)

SPREAD_COST_BPS = Gauge(
    'quantumtrade_spread_cost_basis_points',
    'Spread cost component in basis points',
    ['symbol', 'side'],
)

IMPACT_COST_BPS = Gauge(
    'quantumtrade_impact_cost_basis_points',
    'Market impact cost in basis points',
    ['symbol', 'side', 'algorithm'],
)

IMPL_SHORTFALL_BPS = Gauge(
    'quantumtrade_implementation_shortfall_bps',
    'Implementation shortfall in basis points',
    ['symbol', 'side', 'algorithm'],
)

CHILD_ORDERS_TOTAL = Counter(
    'quantumtrade_child_orders_total',
    'Total child orders generated by algorithms',
    ['algorithm', 'parent_order_id'],
)

FILL_LATENCY_SECONDS = Histogram(
    'quantumtrade_fill_latency_seconds',
    'Time from order submission to fill',
    ['broker', 'algorithm'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ─────────────────────────────────────────
# Strategy Metrics
# ─────────────────────────────────────────

SIGNALS_GENERATED_TOTAL = Counter(
    'quantumtrade_signals_generated_total',
    'Total trading signals generated by strategies',
    ['strategy', 'signal_type'],  # signal_type: BUY, SELL, HOLD
)

STRATEGY_CONFIDENCE = Gauge(
    'quantumtrade_strategy_confidence',
    'Rolling average confidence score for each strategy',
    ['strategy'],
)

STRATEGY_WIN_RATE = Gauge(
    'quantumtrade_strategy_win_rate',
    'Rolling win rate for each strategy',
    ['strategy'],
)

STRATEGY_SHARPE_RATIO = Gauge(
    'quantumtrade_strategy_sharpe_ratio',
    'Sharpe ratio for each strategy',
    ['strategy', 'timeframe'],  # timeframe: 1d, 1w, 1m
)

STRATEGY_ANNUAL_RETURN = Gauge(
    'quantumtrade_strategy_annual_return_percent',
    'Annualized return percentage for each strategy',
    ['strategy'],
)

# ─────────────────────────────────────────
# Risk Metrics
# ─────────────────────────────────────────

PORTFOLIO_VAR_95 = Gauge(
    'quantumtrade_portfolio_var_95',
    '1-day Value at Risk at 95% confidence level (positive number)',
)

PORTFOLIO_VAR_99 = Gauge(
    'quantumtrade_portfolio_var_99',
    '1-day Value at Risk at 99% confidence level',
)

MAX_DRAWDOWN_PERCENT = Gauge(
    'quantumtrade_max_drawdown_percent',
    'Maximum drawdown from peak as percentage',
)

CURRENT_DRAWDOWN_PERCENT = Gauge(
    'quantumtrade_current_drawdown_percent',
    'Current drawdown from peak as percentage',
)

POSITION_CONCENTRATION_RATIO = Gauge(
    'quantumtrade_position_concentration_ratio',
    'Top 5 positions value / total portfolio value (0-1)',
)

DAILY_PNL_USD = Gauge(
    'quantumtrade_daily_pnl_usd',
    'Profit/Loss for current day in USD',
)

RISK_LIMIT_BREACHES_TOTAL = Counter(
    'quantumtrade_risk_limit_breaches_total',
    'Total number of risk limit breaches',
    ['limit_type'],  # limit_type: position_size, daily_loss, max_positions, concentration
)

# ─────────────────────────────────────────
# Broker/API Metrics
# ─────────────────────────────────────────

BROKER_API_CALLS_TOTAL = Counter(
    'quantumtrade_broker_api_calls_total',
    'Total broker API calls made',
    ['broker', 'endpoint', 'status'],  # status: success, error, rate_limited
)

BROKER_API_LATENCY_SECONDS = Histogram(
    'quantumtrade_broker_api_latency_seconds',
    'Broker API call latency',
    ['broker', 'endpoint'],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

BROKER_CONNECTION_STATUS = Gauge(
    'quantumtrade_broker_connection_status',
    'Broker connection status (1=connected, 0=disconnected)',
    ['broker'],
)

BROKER_RATE_LIMIT_REMAINING = Gauge(
    'quantumtrade_broker_rate_limit_remaining',
    'Remaining API calls in current rate limit window',
    ['broker'],
)

BROKER_ORDERS_IN_FLIGHT = Gauge(
    'quantumtrade_broker_orders_in_flight',
    'Number of orders submitted but not yet filled/cancelled',
    ['broker'],
)

# ─────────────────────────────────────────
# Database Metrics
# ─────────────────────────────────────────

DB_QUERIES_TOTAL = Counter(
    'quantumtrade_db_queries_total',
    'Total database queries executed',
    ['query_type'],  # query_type: select, insert, update, delete, transaction
)

DB_QUERY_DURATION_SECONDS = Histogram(
    'quantumtrade_db_query_duration_seconds',
    'Database query execution time',
    ['query_type'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

DB_CONNECTIONS_ACTIVE = Gauge(
    'quantumtrade_db_connections_active',
    'Number of active database connections',
)

DB_CONNECTIONS_MAX = Gauge(
    'quantumtrade_db_connections_max',
    'Maximum allowed database connections',
)

DB_QUERY_ERRORS_TOTAL = Counter(
    'quantumtrade_db_query_errors_total',
    'Total database query errors',
    ['error_type'],
)

# ─────────────────────────────────────────
# Message Bus (Redis) Metrics
# ─────────────────────────────────────────

EVENTS_PUBLISHED_TOTAL = Counter(
    'quantumtrade_events_published_total',
    'Total events published to message bus',
    ['event_type', 'stream'],
)

EVENTS_CONSUMED_TOTAL = Counter(
    'quantumtrade_events_consumed_total',
    'Total events consumed from message bus',
    ['event_type', 'handler'],  # handler: trading_engine, risk_engine, etc.
)

CONSUMER_LAG = Gauge(
    'quantumtrade_consumer_lag',
    'Consumer group lag (messages pending)',
    ['stream', 'consumer_group'],
)

MESSAGE_BUS_CONNECTION_STATUS = Gauge(
    'quantumtrade_message_bus_connection_status',
    'Message bus connection status (1=connected, 0=disconnected)',
)

MESSAGE_BUS_MESSAGES_IN_QUEUE = Gauge(
    'quantumtrade_message_bus_messages_in_queue',
    'Approximate number of messages in each stream',
    ['stream'],
)

# ─────────────────────────────────────────
# Scheduler Metrics
# ─────────────────────────────────────────

SCHEDULER_TICKS_TOTAL = Counter(
    'quantumtrade_scheduler_ticks_total',
    'Total number of scheduler ticks executed',
)

SCHEDULER_ERRORS_TOTAL = Counter(
    'quantumtrade_scheduler_errors_total',
    'Total number of scheduler errors',
)

MARKET_SESSION_TRANSITIONS_TOTAL = Counter(
    'quantumtrade_market_session_transitions_total',
    'Market session transitions',
    ['from_session', 'to_session'],
)

# ─────────────────────────────────────────
# Notification Metrics
# ─────────────────────────────────────────

NOTIFICATIONS_SENT_TOTAL = Counter(
    'quantumtrade_notifications_sent_total',
    'Total notifications sent',
    ['channel', 'level'],  # channel: telegram, discord, email; level: info, warning, error
)

NOTIFICATION_ERRORS_TOTAL = Counter(
    'quantumtrade_notification_errors_total',
    'Total notification delivery errors',
    ['channel'],
)

# ─────────────────────────────────────────
# Machine Learning Metrics
# ─────────────────────────────────────────

ML_PREDICTIONS_TOTAL = Counter(
    'quantumtrade_ml_predictions_total',
    'Total ML model predictions made',
    ['model_name', 'outcome'],
)

MODEL_CONFIDENCE_SCORE = Gauge(
    'quantumtrade_model_confidence_score',
    'Average confidence score for model predictions',
    ['model_name'],
)

MODEL_INFERENCE_LATENCY = Histogram(
    'quantumtrade_model_inference_latency_seconds',
    'Time taken for model inference',
    ['model_name'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# ─────────────────────────────────────────
# Combined/Application Metrics
# ─────────────────────────────────────────

APP_UPTIME_SECONDS = Gauge(
    'quantumtrade_app_uptime_seconds',
    'Application uptime in seconds',
)

ERRORS_TOTAL = Counter(
    'quantumtrade_errors_total',
    'Total unhandled errors',
    ['component', 'error_type'],
)

# ─────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────

def setup_metrics_endpoint(port: Optional[int] = None) -> None:
    """Start the Prometheus HTTP metrics endpoint.

    Args:
        port: Port to listen on (default: 8000 or METRICS_PORT env var)

    Note:
        This starts a daemon HTTP server that exposes /metrics endpoint.
        Call this once at application startup.
    """
    import os

    if port is None:
        port = int(os.getenv('METRICS_PORT', '8000'))

    try:
        start_http_server(port)
        print(f"✅ Prometheus metrics endpoint started on http://localhost:{port}/metrics")
    except OSError as e:
        if e.errno == 98:  # Address already in use
            print(f"⚠️  Metrics endpoint already running on port {port}")
        else:
            raise


def reset_all_metrics() -> None:
    """Reset all metrics to initial values (for testing)."""
    # Note: prometheus_client doesn't provide a clean reset
    # In production, use separate registry or restart process
    pass


# Alias for backward compatibility
start_metrics_server = setup_metrics_endpoint
