"""
Portfolio Risk Engine — Enterprise-grade risk management system.

Calculates comprehensive risk metrics for the QuantumTrade portfolio:
- Value at Risk (Historical, Parametric, Expected Shortfall)
- Exposure analysis (gross, net, sector, asset class)
- Correlation matrix and diversification metrics
- Beta to benchmark (SPY/BTC)
- Stress test scenarios (2008 crisis, 2020 COVID, etc.)
- Real-time limit checking

Performance: <500ms for 20-position portfolio using vectorized numpy/pandas.

Integration:
- Redis cache for price data (1-hour TTL)
- Message bus for RiskEvent publishing (every 5 minutes)
- RiskManager for position-level and portfolio-level checks
"""

import asyncio
import hashlib
import json
import logging
import time  # Added missing import
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from scipy import stats

from .models import (
    Position,
    Exposure,
    RiskLimits,
    RiskBreach,
    PortfolioVaR,
    CorrelationMetrics,
    DrawdownMetrics,
    RiskReport,
    StressScenario,
)
from .var import VaRCalculator
from .exposure import ExposureCalculator
from .correlation import CorrelationAnalyzer
from .stress import StressTester
from .limits import RiskLimitChecker

# Attempt to import Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Message bus and RiskEvent are optional (may not exist yet)
MESSAGING_AVAILABLE = False
MessageBus = None
RiskEvent = None

# Try to import Messaging components if they exist
try:
    from quantumtrade.infrastructure.messaging import MessageBus, RiskEvent
    MESSAGING_AVAILABLE = True
except ImportError:
    # Infrastructure messaging not yet implemented — risk engine will work without it
    pass

logger = logging.getLogger(__name__)


class PortfolioRiskEngine:
    """
    Enterprise-grade portfolio risk management engine.

    Calculates a comprehensive set of risk metrics in near real-time.
    Designed for high performance with vectorized operations and intelligent caching.

    Args:
        broker: Broker connection for portfolio/position data
        data_client: Data client for fetching historical price data
        lookback_days: Number of historical days for VaR calculations (default: 250)
        redis_client: Optional Redis client for caching price data
        message_bus: Optional message bus for publishing RiskEvents
        risk_limits: Optional RiskLimits configuration
        poll_interval_seconds: How often to publish RiskEvent (default: 300 = 5 min)
    """

    def __init__(
        self,
        broker: Optional[Any] = None,
        data_client: Optional[Any] = None,
        lookback_days: int = 250,
        redis_client: Optional[Any] = None,
        message_bus: Optional[Any] = None,
        risk_limits: Optional[RiskLimits] = None,
        poll_interval_seconds: int = 300,
    ):
        self.broker = broker
        self.data_client = data_client
        self.lookback_days = lookback_days
        self.redis = redis_client
        self.message_bus = message_bus
        self.risk_limits = risk_limits or RiskLimits()
        self.poll_interval = poll_interval_seconds

        # Initialize calculators
        self.var_calculator = VaRCalculator(lookback_days=lookback_days)
        self.exposure_calculator = ExposureCalculator()
        self.correlation_analyzer = CorrelationAnalyzer(lookback_days=lookback_days)
        self.stress_tester = StressTester()
        self.limit_checker = RiskLimitChecker()

        # Cache settings
        self.cache_ttl = 3600  # 1 hour in seconds

        # Benchmark symbols
        self.equity_benchmark = "SPY"
        self.crypto_benchmark = "BTC-USD"

        # Internal state
        self._last_risk_report: Optional[RiskReport] = None
        self._last_publish_time: datetime = datetime.min
        self._errors: List[str] = []

        logger.info(
            f"PortfolioRiskEngine initialized: lookback={lookback_days}d, "
            f"poll_interval={poll_interval_seconds}s"
        )

    def calculate_risk_metrics(self) -> RiskReport:
        """
        Main entry point — calculate all portfolio risk metrics.

        Returns:
            RiskReport: Comprehensive risk report with all metrics

        Note:
            Any failures in individual metric calculations are logged and
            stored in report.errors, but do not crash the entire calculation.
        """
        start_time = time.perf_counter()
        self._errors = []

        logger.info("Starting risk metrics calculation...")

        try:
            # 1. Get current portfolio state
            positions, cash, portfolio_value = self._get_portfolio_state()
            logger.debug(
                f"Portfolio: {len(positions)} positions, "
                f"value=${portfolio_value:,.2f}, cash=${cash:,.2f}"
            )

            # 2. Calculate exposures
            exposure = self.exposure_calculator.calculate_exposure(positions, portfolio_value)
            sector_exposure = self.exposure_calculator.calculate_sector_exposure(
                positions, portfolio_value
            )
            concentration = self.exposure_calculator.calculate_concentration(
                positions, portfolio_value
            )

            # 3. Calculate VaR and ES
            portfolio_returns = self._fetch_portfolio_returns(positions)
            var_metrics = self._calculate_var(portfolio_returns, portfolio_value)

            # 4. Calculate correlation matrix and beta
            returns_df = self._fetch_returns_dataframe(positions)
            correlation_metrics = self._calculate_correlation_metrics(returns_df, positions)
            beta = self._calculate_beta(portfolio_returns, positions)

            # 5. Calculate drawdown metrics
            drawdown_metrics = self._calculate_drawdown_metrics()

            # 6. Run stress tests
            sector_map = {p.symbol: p.sector or "Unknown" for p in positions}
            stress_results = self.stress_tester.run_all_scenarios(positions, sector_map)

            # 7. Check risk limits
            breaches = self.limit_checker.check_all_limits(
                positions=positions,
                exposure=exposure,
                portfolio_value=portfolio_value,
                var=var_metrics,
                limits=self.risk_limits,
                sector_exposure=sector_exposure,
            )

            # 8. Create report
            report = RiskReport(
                timestamp=datetime.now(),
                portfolio_value=portfolio_value,
                cash=cash,
                total_exposure=exposure,
                position_count=len(positions),
                concentration_top5_pct=concentration,
                var=var_metrics,
                correlation=correlation_metrics,
                drawdown=drawdown_metrics,
                sector_exposure=sector_exposure,
                beta_to_benchmark=beta,
                stress_test_results=stress_results,
                breaches=breaches,
                errors=self._errors,
            )

            self._last_risk_report = report

            elapsed = time.perf_counter() - start_time
            logger.info(
                f"Risk calculation completed in {elapsed:.3f}s: "
                f"VaR95=${var_metrics.var_95:,.2f}, "
                f"gross_exp={exposure.gross_exposure_pct:.1%}, "
                f"breaches={len(breaches)}"
            )

            # Publish to message bus if enabled and interval elapsed
            self._maybe_publish_event(report)

            return report

        except Exception as e:
            logger.error(f"Risk calculation failed: {e}", exc_info=True)
            self._errors.append(f"Fatal error: {e}")
            # Return partial report with error flag
            return self._create_error_report(e, portfolio_value if 'portfolio_value' in locals() else 0.0)

    def _get_portfolio_state(self) -> Tuple[List[Position], float, float]:
        """
        Retrieve current portfolio positions, cash, and total value.

        Returns:
            Tuple of (positions, cash, portfolio_value)
        """
        if self.broker is None:
            logger.warning("No broker provided — returning empty portfolio")
            return [], 0.0, 0.0

        try:
            # Get account balance
            cash = self.broker.get_balance() if hasattr(self.broker, 'get_balance') else 0.0

            # Get positions
            positions = []
            if hasattr(self.broker, 'get_positions'):
                raw_positions = self.broker.get_positions()
                for pos_dict in raw_positions:
                    pos = Position(
                        symbol=pos_dict['symbol'],
                        quantity=pos_dict['quantity'],
                        avg_entry_price=pos_dict.get('avg_entry_price', pos_dict.get('avg_price', 0.0)),
                        current_price=pos_dict.get('current_price', 0.0),
                        sector=pos_dict.get('sector'),
                        asset_class=pos_dict.get('asset_class'),
                    )
                    positions.append(pos)

            portfolio_value = cash + sum(p.market_value for p in positions)
            return positions, cash, portfolio_value

        except Exception as e:
            logger.error(f"Failed to get portfolio state: {e}")
            self._errors.append(f"Portfolio state fetch error: {e}")
            return [], 0.0, 0.0

    def _fetch_portfolio_returns(self, positions: List[Position]) -> np.ndarray:
        """
        Fetch historical returns for the entire portfolio.

        Returns:
            Array of daily portfolio returns (as decimals, e.g., 0.01 = 1%)
        """
        if not positions:
            logger.debug("No positions — returning empty returns array")
            return np.array([])

        # Collect symbols
        symbols = [p.symbol for p in positions]
        weights = {
            p.symbol: p.market_value / sum(p.market_value for p in positions)
            for p in positions if sum(p.market_value for p in positions) > 0
        }

        # Fetch price history for all symbols (cached)
        price_data = self._fetch_historical_prices(symbols)

        if not price_data:
            logger.warning("No price data fetched — returning empty returns")
            return np.array([])

        # Calculate weighted portfolio returns
        all_returns = []
        for symbol, df in price_data.items():
            if df is None or df.empty or len(df) < 2:
                continue
            # Daily returns
            returns = df['Close'].pct_change().dropna().values
            all_returns.append(returns * weights.get(symbol, 0.0))

        if not all_returns:
            return np.array([])

        # Sum weighted returns (assuming aligned dates — simplified)
        min_len = min(len(r) for r in all_returns)
        portfolio_returns = np.zeros(min_len)
        for returns in all_returns:
            portfolio_returns += returns[-min_len:]

        return portfolio_returns

    def _fetch_returns_dataframe(self, positions: List[Position]) -> pd.DataFrame:
        """
        Fetch returns matrix for all holdings (for correlation).

        Returns:
            DataFrame with dates as index, symbols as columns, values = daily returns
        """
        if not positions:
            return pd.DataFrame()

        symbols = [p.symbol for p in positions]
        price_data = self._fetch_historical_prices(symbols)

        returns_dict = {}
        for symbol, df in price_data.items():
            if df is not None and not df.empty and len(df) >= 2:
                returns_dict[symbol] = df['Close'].pct_change().dropna()

        if not returns_dict:
            return pd.DataFrame()

        returns_df = pd.DataFrame(returns_dict)
        return returns_df.dropna()

    def _fetch_historical_prices(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical OHLCV data for multiple symbols with caching.

        Uses Redis cache (1-hour TTL) if available, otherwise fetches directly.

        Args:
            symbols: List of ticker symbols

        Returns:
            Dict mapping symbol → DataFrame with OHLCV data
        """
        results: Dict[str, Optional[pd.DataFrame]] = {}

        # Check cache first (if Redis available)
        if self.redis and REDIS_AVAILABLE:
            cached_data = self._get_cached_prices(symbols)
            if cached_data:
                results.update(cached_data)
                # Filter out already cached symbols
                symbols_to_fetch = [s for s in symbols if s not in cached_data]
            else:
                symbols_to_fetch = symbols
        else:
            symbols_to_fetch = symbols

        if not symbols_to_fetch:
            return results

        # Fetch remaining symbols in parallel (max 5 workers)
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_symbol = {
                executor.submit(self._fetch_single_symbol, sym): sym
                for sym in symbols_to_fetch
            }
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    results[symbol] = future.result()
                except Exception as e:
                    logger.error(f"Failed to fetch {symbol}: {e}")
                    self._errors.append(f"Price fetch error for {symbol}: {e}")
                    results[symbol] = None

        # Cache successful fetches
        if self.redis and REDIS_AVAILABLE:
            self._cache_prices(results)

        return {k: v for k, v in results.items() if v is not None}

    def _fetch_single_symbol(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLCV data for a single symbol.

        Args:
            symbol: Ticker symbol

        Returns:
            DataFrame with OHLCV data or None on failure
        """
        try:
            if self.data_client is not None:
                # Use provided data client
                df = self.data_client.get_historical_data(
                    symbol, period=f"{self.lookback_days}d", interval="1d"
                )
            else:
                # Fallback to yfinance directly
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=f"{self.lookback_days}d", interval="1d")

            if df is None or df.empty:
                logger.warning(f"No data returned for symbol: {symbol}")
                return None

            # Ensure we have required columns and index is datetime
            if 'Close' not in df.columns:
                logger.warning(f"Missing 'Close' column for {symbol}")
                return None

            # Keep only OHLCV
            expected_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            available_cols = [c for c in expected_cols if c in df.columns]
            df = df[available_cols].copy()

            # Sort by date
            df.sort_index(inplace=True)

            logger.debug(f"Fetched {len(df)} rows for {symbol}")
            return df

        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None

    def _get_cached_prices(self, symbols: List[str]) -> Dict[str, Optional[pd.DataFrame]]:
        """
        Retrieve cached price data from Redis.

        Args:
            symbols: List of symbols to retrieve

        Returns:
            Dict mapping symbol → DataFrame or None if not in cache
        """
        if not self.redis or not REDIS_AVAILABLE:
            return {}

        results = {}
        try:
            # Create cache key from symbols list
            symbols_sorted = sorted(symbols)
            symbols_hash = hashlib.md5(":".join(symbols_sorted).encode()).hexdigest()
            cache_key = f"portfolio_prices:{symbols_hash}"

            # Try to get from Redis
            cached = self.redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                # Reconstruct DataFrames
                for symbol, records in data.items():
                    if records:
                        df = pd.DataFrame(records)
                        df.index = pd.to_datetime(df.index)
                        results[symbol] = df
                    else:
                        results[symbol] = None
                logger.debug(f"Cache hit for {len(results)} symbols")
        except Exception as e:
            logger.debug(f"Redis cache get error: {e}")

        return results

    def _cache_prices(self, price_data: Dict[str, pd.DataFrame]) -> None:
        """
        Store price data in Redis cache with 1-hour TTL.

        Args:
            price_data: Dict mapping symbol → DataFrame
        """
        if not self.redis or not REDIS_AVAILABLE:
            return

        try:
            # Serialize DataFrames to dict
            serializable = {}
            for symbol, df in price_data.items():
                if df is not None and not df.empty:
                    # Convert to records preserving index as string
                    df_copy = df.copy()
                    df_copy.index = df_copy.index.astype(str)
                    serializable[symbol] = df_copy.to_dict(orient='index')
                else:
                    serializable[symbol] = None

            symbols_hash = hashlib.md5(
                ":".join(sorted(price_data.keys())).encode()
            ).hexdigest()
            cache_key = f"portfolio_prices:{symbols_hash}"

            self.redis.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(serializable)
            )
            logger.debug(f"Cached {len(price_data)} symbols")
        except Exception as e:
            logger.debug(f"Redis cache set error: {e}")

    def _calculate_var(
        self,
        portfolio_returns: np.ndarray,
        portfolio_value: float
    ) -> PortfolioVaR:
        """
        Calculate Value at Risk using historical simulation.

        Args:
            portfolio_returns: Array of historical portfolio returns
            portfolio_value: Current portfolio value for scaling

        Returns:
            PortfolioVaR object with 95% and 99% metrics
        """
        if len(portfolio_returns) < 20:
            logger.warning(f"Insufficient returns data for VaR: {len(portfolio_returns)} < 20")
            return PortfolioVaR()

        var_metrics = self.var_calculator.calculate_portfolio_var(
            portfolio_returns,
            portfolio_value,
            confidence_levels=(0.95, 0.99)
        )
        return var_metrics

    def _calculate_correlation_metrics(
        self,
        returns_df: pd.DataFrame,
        positions: List[Position]
    ) -> CorrelationMetrics:
        """
        Calculate correlation matrix and diversification metrics.

        Args:
            returns_df: DataFrame with symbol returns as columns
            positions: List of positions (for weights)

        Returns:
            CorrelationMetrics object
        """
        if returns_df.empty or len(positions) < 2:
            logger.debug("Insufficient data for correlation analysis")
            return CorrelationMetrics()

        metrics = self.correlation_analyzer.calculate_metrics(returns_df)
        return metrics

    def _calculate_beta(
        self,
        portfolio_returns: np.ndarray,
        positions: List[Position]
    ) -> float:
        """
        Calculate portfolio beta to appropriate benchmark.

        Auto-detects asset class: uses SPY for equities, BTC-USD for crypto.

        Args:
            portfolio_returns: Portfolio return series
            positions: Current positions

        Returns:
            Beta coefficient (float)
        """
        if len(portfolio_returns) < 20:
            return 1.0

        # Determine benchmark based on asset types
        asset_classes = [p.asset_class for p in positions if p.asset_class]
        if any(ac and "crypto" in ac.lower() for ac in asset_classes):
            benchmark_symbol = self.crypto_benchmark
        else:
            benchmark_symbol = self.equity_benchmark

        # Fetch benchmark returns
        benchmark_returns = self._fetch_benchmark_returns(benchmark_symbol)
        if benchmark_returns is None or len(benchmark_returns) < 20:
            logger.debug(f"Insufficient benchmark data for {benchmark_symbol}")
            return 1.0

        beta = self.correlation_analyzer.calculate_beta_to_benchmark(
            portfolio_returns,
            benchmark_returns
        )
        logger.debug(f"Portfolio beta to {benchmark_symbol}: {beta:.3f}")
        return beta

    def _fetch_benchmark_returns(self, symbol: str) -> Optional[np.ndarray]:
        """Fetch benchmark returns series."""
        try:
            df = self._fetch_single_symbol(symbol)
            if df is not None and len(df) >= 2:
                returns = df['Close'].pct_change().dropna().values
                return returns[-self.lookback_days:] if len(returns) > self.lookback_days else returns
        except Exception as e:
            logger.error(f"Failed to fetch benchmark {symbol}: {e}")
        return None

    def _calculate_drawdown_metrics(self) -> DrawdownMetrics:
        """
        Calculate drawdown metrics from portfolio value history.

        Returns:
            DrawdownMetrics with current and peak values
        """
        # In live trading, this would be populated from equity curve
        # For now, return placeholder (RiskManager tracks this)
        return DrawdownMetrics(
            current_drawdown=0.0,
            max_drawdown=0.0,
            days_underwater=0,
            peak_value=0.0,
            current_value=0.0,
        )

    def _maybe_publish_event(self, report: RiskReport) -> None:
        """
        Publish RiskEvent to message bus if interval has elapsed.

        Args:
            report: Current risk report
        """
        # Skip if messaging not configured or not available
        if not self.message_bus or not MESSAGING_AVAILABLE or RiskEvent is None:
            return

        now = datetime.now()
        if (now - self._last_publish_time).total_seconds() < self.poll_interval:
            return  # Not yet time to publish

        try:
            event = RiskEvent(
                event_type="risk_update",
                timestamp=now,
                data=report.to_dict()
            )
            # Async publish if possible, else sync
            if hasattr(self.message_bus, 'publish_async'):
                asyncio.create_task(self.message_bus.publish_async(event))
            else:
                self.message_bus.publish(event)

            self._last_publish_time = now
            logger.debug(f"Published RiskEvent with VaR95=${report.var.var_95:,.2f}")

        except Exception as e:
            logger.error(f"Failed to publish RiskEvent: {e}")
            if hasattr(self, '_errors'):
                self._errors.append(f"Message bus publish error: {e}")

    def _create_error_report(self, error: Exception, portfolio_value: float = 0.0) -> RiskReport:
        """Create minimal report when calculation fails catastrophically."""
        return RiskReport(
            timestamp=datetime.now(),
            portfolio_value=portfolio_value,
            cash=0.0,
            total_exposure=Exposure(),
            position_count=0,
            concentration_top5_pct=0.0,
            var=PortfolioVaR(),
            correlation=CorrelationMetrics(),
            drawdown=DrawdownMetrics(),
            sector_exposure={},
            beta_to_benchmark=1.0,
            stress_test_results={},
            breaches=[],
            errors=[f"Fatal calculation error: {error}"]
        )

    def get_last_report(self) -> Optional[RiskReport]:
        """Retrieve the most recent risk report."""
        return self._last_risk_report

    def update_limits(self, new_limits: RiskLimits) -> None:
        """Update risk limits configuration."""
        self.risk_limits = new_limits
        logger.info(f"Risk limits updated: {new_limits.to_dict()}")
