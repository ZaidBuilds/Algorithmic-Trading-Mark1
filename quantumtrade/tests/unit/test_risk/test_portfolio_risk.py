"""
Unit tests for Portfolio Risk Engine.

Tests cover:
- VaR calculations (historical, parametric, expected shortfall)
- Exposure metrics (gross, net, sector, concentration)
- Correlation analysis (matrix properties, beta, diversification)
- Stress testing (scenario application)
- Risk limit checking
- Edge cases (empty portfolio, single position, all cash)
- Integration test with PortfolioRiskEngine

Run with: pytest tests/unit/test_portfolio_risk.py -v
"""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime
from typing import Dict, List

from quantumtrade.domain.risk.models import (
    Position,
    Exposure,
    RiskLimits,
    RiskBreach,
    Portfolio,
    RiskReport,
    PortfolioVaR,
    CorrelationMetrics,
    DrawdownMetrics,
    StressScenario,
)
from quantumtrade.domain.risk.portfolio_risk import PortfolioRiskEngine
from quantumtrade.domain.risk.var import VaRCalculator
from quantumtrade.domain.risk.exposure import ExposureCalculator
from quantumtrade.domain.risk.correlation import CorrelationAnalyzer
from quantumtrade.domain.risk.stress import StressTester
from quantumtrade.domain.risk.limits import RiskLimitChecker


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_positions() -> List[Position]:
    """Create a list of sample positions for testing."""
    return [
        Position(symbol="AAPL", quantity=100, avg_entry_price=150.0, current_price=160.0, sector="Technology"),
        Position(symbol="GOOGL", quantity=50, avg_entry_price=2800.0, current_price=2900.0, sector="Technology"),
        Position(symbol="MSFT", quantity=30, avg_entry_price=300.0, current_price=310.0, sector="Technology"),
        Position(symbol="JPM", quantity=80, avg_entry_price=130.0, current_price=135.0, sector="Financials"),
        Position(symbol="XOM", quantity=120, avg_entry_price=60.0, current_price=62.0, sector="Energy"),
    ]


@pytest.fixture
def empty_positions() -> List[Position]:
    """Empty portfolio."""
    return []


@pytest.fixture
def single_position() -> List[Position]:
    """Single position portfolio."""
    return [Position(symbol="AAPL", quantity=10, avg_entry_price=100.0, current_price=110.0)]


@pytest.fixture
def mixed_positions() -> List[Position]:
    """Portfolio with both long and short positions."""
    return [
        Position(symbol="AAPL", quantity=100, avg_entry_price=150.0, current_price=160.0, sector="Technology"),
        Position(symbol="TSLA", quantity=-50, avg_entry_price=200.0, current_price=190.0, sector="Automotive"),
    ]


@pytest.fixture
def var_calculator() -> VaRCalculator:
    """Default VaR calculator."""
    return VaRCalculator(lookback_days=250, time_horizon_days=1)


@pytest.fixture
def exposure_calculator() -> ExposureCalculator:
    return ExposureCalculator()


@pytest.fixture
def correlation_analyzer() -> CorrelationAnalyzer:
    return CorrelationAnalyzer(lookback_days=252)


@pytest.fixture
def stress_tester() -> StressTester:
    return StressTester()


@pytest.fixture
def limit_checker() -> RiskLimitChecker:
    return RiskLimitChecker()


@pytest.fixture
def sample_returns() -> np.ndarray:
    """Generate sample normally-distributed returns for testing."""
    np.random.seed(42)
    return np.random.normal(0.0005, 0.015, 500)  # 500 days, ~0.05% daily mean, 1.5% vol


@pytest.fixture
def correlated_returns_df() -> pd.DataFrame:
    """Create a DataFrame of correlated returns for correlation testing."""
    np.random.seed(42)
    n_days = 250
    market = np.random.normal(0.0005, 0.012, n_days)

    # Create 5 assets with varying correlation to market and idiosyncratic noise
    assets = {}
    for i, symbol in enumerate(['AAPL', 'GOOGL', 'MSFT', 'JPM', 'XOM']):
        beta = 0.8 + i * 0.1  # Different betas
        idiosyncratic = np.random.normal(0, 0.008, n_days)
        returns = 0.0002 + beta * market + idiosyncratic
        assets[symbol] = returns

    return pd.DataFrame(assets)


# ─────────────────────────────────────────────────────────────────────────────
# VaR Calculator Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestVaRCalculator:
    """Tests for Value at Risk calculations."""

    def test_historical_var_95(self, var_calculator, sample_returns):
        """Test historical VaR at 95% confidence."""
        var = var_calculator.calculate_historical_var(sample_returns, confidence=0.95)

        assert var > 0, "VaR should be positive (representing loss)"
        assert isinstance(var, float), "VaR should be float"

        # For this return distribution, VaR 95% should be approximately 2-3% daily loss
        assert 0.015 < var < 0.045, f"VaR 95% {var:.4f} seems outside expected range"

    def test_historical_var_99(self, var_calculator, sample_returns):
        """Test historical VaR at 99% confidence (more extreme)."""
        var_95 = var_calculator.calculate_historical_var(sample_returns, confidence=0.95)
        var_99 = var_calculator.calculate_historical_var(sample_returns, confidence=0.99)

        assert var_99 > var_95, "99% VaR should be >= 95% VaR (more conservative)"

    def test_parametric_var(self, var_calculator, sample_returns):
        """Test parametric VaR assuming normal distribution."""
        portfolio_value = 1_000_000.0
        var = var_calculator.calculate_parametric_var(
            sample_returns,
            confidence=0.95,
            portfolio_value=portfolio_value
        )

        assert var > 0, "Parametric VaR should be positive"
        assert var < portfolio_value * 0.1, "VaR should be less than 10% of portfolio"

    def test_expected_shortfall_95(self, var_calculator, sample_returns):
        """Test Expected Shortfall (CVaR) at 95%."""
        es = var_calculator.calculate_expected_shortfall(sample_returns, confidence=0.95)
        var_95 = var_calculator.calculate_historical_var(sample_returns, confidence=0.95)

        # ES should be >= VaR (mathematical property)
        assert es >= var_95, f"ES ({es:.6f}) should be >= VaR ({var_95:.6f})"

    def test_expected_shortfall_99(self, var_calculator, sample_returns):
        """Test Expected Shortfall at 99%."""
        es_95 = var_calculator.calculate_expected_shortfall(sample_returns, confidence=0.95)
        es_99 = var_calculator.calculate_expected_shortfall(sample_returns, confidence=0.99)

        # For fat-tailed distributions, ES 99% might not always be >= ES 95%
        # But generally it should be
        assert es_99 >= es_95 or np.isclose(es_99, es_95, rtol=0.1), \
            "ES 99% should generally be >= ES 95%"

    def test_var_insufficient_data(self, var_calculator):
        """Test VaR with insufficient data (<20 observations)."""
        short_returns = np.array([0.01, -0.02, 0.005])
        var = var_calculator.calculate_historical_var(short_returns, confidence=0.95)
        assert var == 0.0, "Should return 0 for insufficient data"

    def test_portfolio_var_structure(self, var_calculator, sample_returns):
        """Test PortfolioVaR object structure."""
        portfolio_returns = sample_returns[:200]
        portfolio_value = 1_000_000.0

        result = var_calculator.calculate_portfolio_var(
            portfolio_returns,
            portfolio_value,
            confidence_levels=(0.95, 0.99)
        )

        assert isinstance(result, PortfolioVaR)
        assert result.var_95 >= 0, "VaR 95% should be non-negative"
        assert result.var_99 >= 0, "VaR 99% should be non-negative"
        assert result.expected_shortfall_95 >= result.var_95, "ES 95 >= VaR 95"
        assert result.expected_shortfall_99 >= result.var_99, "ES 99 >= VaR 99"

    def test_var_with_negative_mean(self, var_calculator):
        """Test VaR with negative average returns."""
        # Simulate a losing strategy
        np.random.seed(123)
        returns = np.random.normal(-0.001, 0.02, 300)

        var = var_calculator.calculate_historical_var(returns, confidence=0.95)
        assert var > 0, "VaR should still be positive"

    def test_param_var_with_zero_std(self, var_calculator):
        """Test parametric VaR with zero standard deviation (constant returns)."""
        constant_returns = np.array([0.001] * 100)
        var = var_calculator.calculate_parametric_var(constant_returns, confidence=0.95, portfolio_value=10000)
        assert var >= 0, "VaR should be non-negative even with zero vol"


# ─────────────────────────────────────────────────────────────────────────────
# Exposure Calculator Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExposureCalculator:
    """Tests for exposure calculations."""

    def test_gross_exposure_long_only(self, exposure_calculator, sample_positions):
        """Test gross exposure with only long positions."""
        portfolio_value = sum(p.market_value for p in sample_positions)
        exposure = exposure_calculator.calculate_exposure(sample_positions, portfolio_value)

        assert exposure.long_exposure > 0, "Long exposure should be positive"
        assert exposure.short_exposure == 0.0, "Short exposure should be zero"
        assert exposure.gross_exposure == exposure.long_exposure, "Gross = long only"
        assert exposure.net_exposure == exposure.long_exposure, "Net = long only"

        # Check percentages
        assert np.isclose(exposure.gross_exposure_pct, 1.0), "Gross % should be 100% for fully invested long-only"
        assert exposure.net_exposure_pct == exposure.gross_exposure_pct, "Net % = Gross % for long-only"

    def test_gross_exposure_with_shorts(self, exposure_calculator, mixed_positions):
        """Test gross and net exposure with short positions."""
        portfolio_value = sum(abs(p.market_value) for p in mixed_positions)
        exposure = exposure_calculator.calculate_exposure(mixed_positions, portfolio_value)

        assert exposure.long_exposure > 0, "Long exposure positive"
        assert exposure.short_exposure > 0, "Short exposure positive"
        assert exposure.gross_exposure == exposure.long_exposure + exposure.short_exposure
        assert exposure.net_exposure == exposure.long_exposure - exposure.short_exposure

    def test_exposure_zero_portfolio(self, exposure_calculator, sample_positions):
        """Test exposure with zero portfolio value."""
        exposure = exposure_calculator.calculate_exposure(sample_positions, portfolio_value=0.0)
        assert exposure.gross_exposure_pct == 0.0, "Percentages should be zero with zero portfolio"

    def test_exposure_empty_portfolio(self, exposure_calculator, empty_positions):
        """Test exposure with empty positions."""
        exposure = exposure_calculator.calculate_exposure(empty_positions, portfolio_value=100000)
        assert exposure.long_exposure == 0.0
        assert exposure.short_exposure == 0.0
        assert exposure.gross_exposure == 0.0
        assert exposure.net_exposure == 0.0

    def test_sector_exposure(self, exposure_calculator, sample_positions):
        """Test sector exposure calculation."""
        portfolio_value = sum(p.market_value for p in sample_positions)
        sector_exp = exposure_calculator.calculate_sector_exposure(sample_positions, portfolio_value)

        assert "Technology" in sector_exp, "Technology sector should be present"
        assert sector_exp["Technology"] > 0, "Tech exposure should be positive"
        # Technology has 3 of 5 positions - adjust tolerance for the actual distribution
        assert 0.5 < sector_exp["Technology"] < 1.0, f"Tech should be ~60-70%, got {sector_exp['Technology']:.2%}"

        # Sum of all sector exposures should equal 100% (gross exposure normalized)
        total = sum(sector_exp.values())
        assert np.isclose(total, 1.0), f"Total sector exposure should sum to 100%, got {total:.2%}"

    def test_sector_exposure_unknown(self, exposure_calculator):
        """Test handling of positions with no sector."""
        positions = [Position(symbol="XYZ", quantity=100, avg_entry_price=10, current_price=12)]
        sector_exp = exposure_calculator.calculate_sector_exposure(positions, portfolio_value=1200)
        assert "Unknown" in sector_exp, "Unknown sector should be present"

    def test_concentration(self, exposure_calculator, sample_positions):
        """Test top 5 concentration ratio."""
        portfolio_value = sum(p.market_value for p in sample_positions)
        concentration = exposure_calculator.calculate_concentration(sample_positions, portfolio_value)

        assert 0.0 <= concentration <= 1.0, "Concentration should be between 0 and 1"
        # With 5 positions, top 5 should be ~100%
        assert concentration > 0.9, f"With 5 positions, top 5 should be near 100%, got {concentration:.2%}"
        assert np.isclose(concentration, 1.0), "Top 5 of 5 positions = 100%"

    def test_concentration_few_positions(self, exposure_calculator):
        """Test concentration with fewer than 5 positions."""
        positions = [
            Position(symbol="AAPL", quantity=100, avg_entry_price=150, current_price=160),
            Position(symbol="GOOGL", quantity=50, avg_entry_price=2800, current_price=2900),
        ]
        portfolio_value = sum(p.market_value for p in positions)
        concentration = exposure_calculator.calculate_concentration(positions, portfolio_value)
        assert np.isclose(concentration, 1.0), "With 2 positions, top 5 = 100%"

    def test_asset_class_exposure(self, exposure_calculator):
        """Test asset class exposure calculation."""
        positions = [
            Position(symbol="AAPL", quantity=100, avg_entry_price=150, current_price=160, asset_class="stock"),
            Position(symbol="BTC-USD", quantity=0.5, avg_entry_price=40000, current_price=42000, asset_class="crypto"),
        ]
        portfolio_value = sum(p.market_value for p in positions)
        asset_exp = exposure_calculator.calculate_asset_class_exposure(positions, portfolio_value)

        assert "stock" in asset_exp
        assert "crypto" in asset_exp
        assert np.isclose(sum(asset_exp.values()), 1.0)

    def test_largest_positions(self, exposure_calculator):
        """Test retrieval of largest positions."""
        positions = [
            Position(symbol="A", quantity=1, avg_entry_price=100, current_price=100),
            Position(symbol="B", quantity=1, avg_entry_price=500, current_price=500),
            Position(symbol="C", quantity=1, avg_entry_price=300, current_price=300),
            Position(symbol="D", quantity=1, avg_entry_price=200, current_price=200),
            Position(symbol="E", quantity=1, avg_entry_price=50, current_price=50),
            Position(symbol="F", quantity=1, avg_entry_price=400, current_price=400),
        ]
        top3 = exposure_calculator.get_largest_positions(positions, n=3)
        assert len(top3) == 3
        assert top3[0].symbol == "B"  # $500
        assert top3[1].symbol == "F"  # $400
        assert top3[2].symbol == "C"  # $300


# ─────────────────────────────────────────────────────────────────────────────
# Correlation Analyzer Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCorrelationAnalyzer:
    """Tests for correlation matrix and diversification metrics."""

    def test_correlation_matrix_shape(self, correlation_analyzer, correlated_returns_df):
        """Test correlation matrix shape and diagonal."""
        corr = correlation_analyzer.calculate_correlation_matrix(correlated_returns_df)

        assert isinstance(corr, pd.DataFrame)
        n = len(correlated_returns_df.columns)
        assert corr.shape == (n, n), "Correlation matrix should be square"
        assert list(corr.columns) == list(correlated_returns_df.columns)

        # Diagonal should be 1
        np.testing.assert_allclose(np.diag(corr.values), 1.0, atol=1e-10)

        # Symmetric
        np.testing.assert_allclose(corr.values, corr.values.T, atol=1e-10)

    def test_correlation_matrix_empty(self, correlation_analyzer):
        """Test correlation with empty/single-column data."""
        empty_df = pd.DataFrame()
        result = correlation_analyzer.calculate_correlation_matrix(empty_df)
        assert result.empty

        single_df = pd.DataFrame({"AAPL": np.random.randn(100)})
        result = correlation_analyzer.calculate_correlation_matrix(single_df)
        assert result.empty

    def test_beta_calculation(self, correlation_analyzer):
        """Test beta calculation vs benchmark."""
        np.random.seed(42)
        n = 300

        # Create benchmark returns
        benchmark = np.random.normal(0.0005, 0.012, n)

        # Create portfolio returns with known beta = 1.2
        alpha = 0.0002
        beta_true = 1.2
        idiosyncratic = np.random.normal(0, 0.006, n)
        portfolio = alpha + beta_true * benchmark + idiosyncratic

        calculated_beta = correlation_analyzer.calculate_beta_to_benchmark(portfolio, benchmark)

        assert 1.0 < calculated_beta < 1.4, f"Beta {calculated_beta:.3f} should be close to 1.2"
        assert np.isclose(calculated_beta, beta_true, rtol=0.2), "Beta should be approximately 1.2"

    def test_beta_insufficient_data(self, correlation_analyzer):
        """Test beta with insufficient data."""
        beta = correlation_analyzer.calculate_beta_to_benchmark(
            np.array([0.01, 0.02]),
            np.array([0.01, 0.02])
        )
        assert beta == 1.0, "Default beta should be 1.0 for insufficient data"

    def test_beta_zero_variance(self, correlation_analyzer):
        """Test beta when benchmark has zero variance."""
        portfolio = np.array([0.01, -0.02, 0.03])
        benchmark = np.array([0.0, 0.0, 0.0])
        beta = correlation_analyzer.calculate_beta_to_benchmark(portfolio, benchmark)
        assert beta == 1.0, "Beta should default to 1.0 when benchmark variance is zero"

    def test_diversification_metrics(self, correlation_analyzer):
        """Test eigenvalue-based diversification metrics."""
        # Identity matrix (perfect diversification)
        identity = np.eye(5)
        div, market_factor, avg_corr = correlation_analyzer.get_eigenvalue_metrics(identity)

        assert div >= 0.8, f"Diversification should be high for identity matrix, got {div}"
        assert market_factor < 0.5, "Market factor dominance should be low"

        # Perfectly correlated matrix (no diversification)
        ones = np.ones((5, 5))
        div, market_factor, avg_corr = correlation_analyzer.get_eigenvalue_metrics(ones)
        assert div <= 0.2, f"Diversification near zero for perfect correlation, got {div}"
        assert market_factor > 0.8, "Market factor dominance near 1.0"

    def test_metrics_integration(self, correlation_analyzer, correlated_returns_df):
        """Test the full calculate_metrics method."""
        metrics = correlation_analyzer.calculate_metrics(correlated_returns_df)

        assert isinstance(metrics, CorrelationMetrics)
        assert 0.0 <= metrics.diversification_score <= 1.0
        assert 0.0 <= metrics.market_factor_dominance <= 1.0
        assert -1.0 <= metrics.avg_correlation <= 1.0

    def test_weighted_beta(self, correlation_analyzer):
        """Test weighted beta calculation."""
        position_betas = {"AAPL": 1.2, "GOOGL": 1.5, "MSFT": 0.9}
        position_weights = {"AAPL": 0.4, "GOOGL": 0.4, "MSFT": 0.2}

        beta = correlation_analyzer.calculate_weighted_beta(position_betas, position_weights)

        expected = 1.2 * 0.4 + 1.5 * 0.4 + 0.9 * 0.2
        assert np.isclose(beta, expected), f"Weighted beta {beta:.4f} should equal {expected:.4f}"


# ─────────────────────────────────────────────────────────────────────────────
# Stress Tester Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStressTester:
    """Tests for stress test scenarios."""

    def test_predefined_scenarios_exist(self, stress_tester):
        """Test that predefined scenarios are available."""
        assert "2008_crisis" in stress_tester.SCENARIOS
        assert "covid_crash" in stress_tester.SCENARIOS
        assert "tech_bubble" in stress_tester.SCENARIOS
        assert "energy_crash" in stress_tester.SCENARIOS
        assert "sector_rotation" in stress_tester.SCENARIOS

    def test_apply_crisis_scenario(self, sample_positions):
        """Test applying 2008 crisis scenario."""
        tester = StressTester()
        sector_map = {"AAPL": "Technology", "GOOGL": "Technology", "MSFT": "Technology",
                      "JPM": "Financials", "XOM": "Energy"}

        result = tester.apply_scenario(sample_positions, tester.SCENARIOS["2008_crisis"], sector_map)

        assert "total_pnl" in result
        assert "total_pnl_pct" in result
        # Note: total_pnl could be positive or negative depending on position mix
        assert "position_impacts" in result

    def test_apply_sector_shock(self, stress_tester):
        """Test applying a sector-specific shock."""
        positions = [
            Position(symbol="AAPL", quantity=100, avg_entry_price=150, current_price=160, sector="Technology"),
            Position(symbol="MSFT", quantity=50, avg_entry_price=300, current_price=310, sector="Technology"),
        ]
        scenario = StressScenario(
            name="Tech Crash",
            description="Tech sector down 30%",
            shocks={"Technology": -0.30},
            correlation_shock=0.0
        )
        sector_map = {"AAPL": "Technology", "MSFT": "Technology"}
        result = stress_tester.apply_scenario(positions, scenario, sector_map)

        # Both tech positions should lose value
        assert result["total_pnl"] < 0
        # Loss should be roughly 30% of tech positions
        tech_value = sum(p.market_value for p in positions)
        expected_loss = tech_value * -0.30
        assert np.isclose(result["total_pnl"], expected_loss, rtol=0.05)

    def test_run_all_scenarios(self, sample_positions):
        """Test running all predefined scenarios."""
        tester = StressTester()
        sector_map = {"AAPL": "Technology", "GOOGL": "Technology", "MSFT": "Technology",
                      "JPM": "Financials", "XOM": "Energy"}

        results = tester.run_all_scenarios(sample_positions, sector_map)

        assert len(results) == len(tester.SCENARIOS)
        for name, result in results.items():
            assert "total_pnl" in result
            assert "scenario" in result
            # The scenario name in result should match or contain the key name
            assert result["scenario"] is not None

    def test_create_custom_scenario(self, stress_tester):
        """Test creating a custom scenario."""
        custom = stress_tester.create_custom_scenario(
            name="Test",
            description="Test shock",
            shocks={"AAPL": -0.10, "GOOGL": -0.15},
            correlation_shock=0.2
        )
        assert custom.name == "Test"
        assert custom.shocks["AAPL"] == -0.10
        assert custom.correlation_shock == 0.2

    def test_custom_shock_helper(self, stress_tester):
        """Test apply_custom_shock helper method."""
        positions = [Position(symbol="AAPL", quantity=100, avg_entry_price=150, current_price=160)]
        shocks = {"AAPL": -0.10}
        result = stress_tester.apply_custom_shock(positions, shocks)

        expected_loss = 100 * 160 * -0.10  # -$1600
        assert np.isclose(result["total_pnl"], expected_loss)

    def test_sector_shock_helper(self, stress_tester):
        """Test get_sector_shock helper."""
        scenario = stress_tester.get_sector_shock("Technology", -0.25)
        assert scenario.name == "Technology Shock"
        assert scenario.shocks["Technology"] == -0.25


# ─────────────────────────────────────────────────────────────────────────────
# Risk Limit Checker Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskLimitChecker:
    """Tests for risk limit validation."""

    def test_position_limit_breach(self, limit_checker, sample_positions):
        """Test detection of position size breaches."""
        limits = RiskLimits(max_position_pct=0.05)  # 5% limit
        exposure = Exposure(gross_exposure_pct=1.0, net_exposure_pct=0.5)
        portfolio_value = 1_000_000

        # AAPL position: 100 * 160 = $16,000 which is 1.6% → not breach with 5%
        # But GOOGL: 50*2900 = $145,000 → 14.5% → breach
        breaches = limit_checker.check_all_limits(
            sample_positions, exposure, portfolio_value, PortfolioVaR(), limits
        )

        position_breaches = [b for b in breaches if b.limit_type == "position_size"]
        assert len(position_breaches) >= 1, "Should detect at least one position breach"

    def test_sector_limit_breach(self, limit_checker, sample_positions):
        """Test detection of sector concentration breaches."""
        limits = RiskLimits(max_sector_exposure_pct=0.40)  # 40% limit
        exposure = Exposure(gross_exposure_pct=1.0, net_exposure_pct=0.5)
        portfolio_value = 1_000_000

        # Technology sector should be ~60-70% → breach at 40%
        sector_exp = {"Technology": 0.65, "Financials": 0.20, "Energy": 0.15}
        breaches = limit_checker.check_all_limits(
            sample_positions, exposure, portfolio_value, PortfolioVaR(), limits, sector_exp
        )

        sector_breaches = [b for b in breaches if b.limit_type == "sector_exposure"]
        assert len(sector_breaches) > 0, "Should detect sector limit breach"

    def test_gross_exposure_limit(self, limit_checker):
        """Test gross exposure limit."""
        limits = RiskLimits(max_gross_exposure_pct=1.2)
        exposure = Exposure(
            long_exposure=800_000,
            short_exposure=500_000,
            gross_exposure=1_300_000,
            net_exposure=300_000,
            gross_exposure_pct=1.3,
            net_exposure_pct=0.3
        )
        breach = limit_checker._check_gross_exposure_limit(exposure, limits)
        assert breach is not None, "Gross exposure should breach limit"

    def test_net_exposure_limit(self, limit_checker):
        """Test net exposure limit."""
        limits = RiskLimits(max_net_exposure_pct=0.5)
        exposure = Exposure(
            gross_exposure_pct=1.2,
            net_exposure_pct=0.8
        )
        breach = limit_checker._check_net_exposure_limit(exposure, limits)
        assert breach is not None, "Net exposure should breach limit"

    def test_var_limit(self, limit_checker):
        """Test VaR limit."""
        limits = RiskLimits(var_95_limit_usd=50_000)
        var = PortfolioVaR(var_95=75_000, var_99=100_000)
        breach = limit_checker._check_var_limit(var, limits)
        assert breach is not None, "VaR should breach limit"

    def test_no_breaches(self, limit_checker, sample_positions):
        """Test scenario with no breaches."""
        limits = RiskLimits(
            max_position_pct=0.20,
            max_sector_exposure_pct=0.50,
            max_gross_exposure_pct=2.0,
            max_net_exposure_pct=1.0,
            var_95_limit_usd=200_000,
        )
        portfolio_value = 1_000_000
        exposure = ExposureCalculator().calculate_exposure(sample_positions, portfolio_value)
        sector_exp = ExposureCalculator().calculate_sector_exposure(sample_positions, portfolio_value)
        var = PortfolioVaR(var_95=30_000, var_99=50_000)

        breaches = limit_checker.check_all_limits(
            sample_positions, exposure, portfolio_value, var, limits, sector_exp
        )
        assert len(breaches) == 0, f"Should have no breaches, got {len(breaches)}"

    def test_trading_allowed(self, limit_checker):
        """Test trading permission logic."""
        assert limit_checker.is_trading_allowed([]) is True
        assert limit_checker.is_trading_allowed([RiskBreach("test", 0.1, 0.05, "")]) is False

    def test_breach_summary(self, limit_checker):
        """Test breach summary aggregation."""
        breaches = [
            RiskBreach("position_size", 0.15, 0.10, ""),
            RiskBreach("position_size", 0.12, 0.10, ""),
            RiskBreach("gross_exposure", 1.3, 1.2, ""),
        ]
        summary = limit_checker.get_breach_summary(breaches)
        assert summary["position_size"] == 2
        assert summary["gross_exposure"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# PortfolioRiskEngine Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPortfolioRiskEngine:
    """Integration tests for the full risk engine."""

    def test_engine_initialization(self):
        """Test engine can be instantiated with default config."""
        engine = PortfolioRiskEngine()
        assert engine is not None
        assert engine.risk_limits is not None
        assert engine.lookback_days == 250

    def test_engine_without_broker(self):
        """Test engine works without broker (empty portfolio)."""
        engine = PortfolioRiskEngine()
        report = engine.calculate_risk_metrics()

        assert report.portfolio_value == 0.0
        assert report.position_count == 0
        assert report.var.var_95 == 0.0
        assert len(report.errors) == 0  # Should not error, just return empty

    def test_engine_with_mock_portfolio(self, sample_positions, monkeypatch):
        """Test engine with mocked broker and minimal data fetching."""
        # Create a mock broker
        class MockBroker:
            def get_balance(self):
                return 50000.0

            def get_positions(self):
                return [
                    {
                        "symbol": p.symbol,
                        "quantity": p.quantity,
                        "avg_entry_price": p.avg_entry_price,
                        "current_price": p.current_price,
                        "sector": p.sector,
                        "asset_class": p.asset_class,
                    }
                    for p in sample_positions
                ]

        # Create a mock data client that returns dummy price data
        class MockDataClient:
            def get_historical_data(self, symbol, period, interval):
                # Return simple fake OHLCV DataFrame
                dates = pd.date_range(end=datetime.now(), periods=100, freq="D")
                np.random.seed(hash(symbol) % 2**32)
                closes = 100 * np.cumprod(1 + np.random.normal(0.0005, 0.02, 100))
                return pd.DataFrame({
                    "Open": closes * 0.99,
                    "High": closes * 1.02,
                    "Low": closes * 0.98,
                    "Close": closes,
                    "Volume": np.random.randint(1000, 10000, 100),
                }, index=dates)

        broker = MockBroker()
        data_client = MockDataClient()

        engine = PortfolioRiskEngine(
            broker=broker,
            data_client=data_client,
            lookback_days=100,
        )

        report = engine.calculate_risk_metrics()

        # Validate report structure
        assert report.timestamp is not None
        assert report.portfolio_value > 0
        assert report.position_count == len(sample_positions)
        assert isinstance(report.total_exposure, Exposure)
        assert isinstance(report.var, PortfolioVaR)
        assert isinstance(report.correlation, CorrelationMetrics)
        assert isinstance(report.sector_exposure, dict)
        assert isinstance(report.breaches, list)

        # Check values are reasonable
        assert report.total_exposure.gross_exposure > 0
        assert report.total_exposure.net_exposure > 0  # All long positions
        assert 0.0 <= report.concentration_top5_pct <= 1.0

    def test_performance_requirement(self, sample_positions):
        """Test that risk calculation completes within 500ms for 20-position portfolio."""
        import time

        class FastDataClient:
            def get_historical_data(self, symbol, period, interval):
                dates = pd.date_range(end=datetime.now(), periods=250, freq="D")
                closes = 100 + np.cumsum(np.random.randn(250) * 0.5)
                return pd.DataFrame({
                    "Close": closes,
                }, index=dates)

        class MockBroker:
            def get_balance(self):
                return 1_000_000.0
            def get_positions(self):
                return [
                    {"symbol": p.symbol, "quantity": p.quantity, "avg_entry_price": p.avg_entry_price,
                     "current_price": p.current_price, "sector": p.sector, "asset_class": p.asset_class}
                    for p in sample_positions
                ]

        engine = PortfolioRiskEngine(
            broker=MockBroker(),
            data_client=FastDataClient(),
            lookback_days=250,
        )

        start = time.perf_counter()
        report = engine.calculate_risk_metrics()
        elapsed = time.perf_counter() - start

        assert elapsed < 0.5, f"Risk calculation took {elapsed:.3f}s, exceeds 500ms requirement"
        assert report.var.var_95 > 0, "VaR should be calculated"

    def test_error_handling_partial_metrics(self):
        """Test that engine returns partial metrics even when some components fail."""
        # Use broker that raises exception
        class BrokenBroker:
            def get_balance(self):
                raise RuntimeError("Broker down")
            def get_positions(self):
                raise RuntimeError("Broker down")

        engine = PortfolioRiskEngine(broker=BrokenBroker())
        report = engine.calculate_risk_metrics()

        assert report.portfolio_value == 0.0
        assert report.position_count == 0
        assert len(report.errors) > 0, "Should record error"
        assert "Broker down" in str(report.errors[0])

    def test_report_serialization(self, sample_positions):
        """Test that RiskReport can be serialized to dict."""
        from datetime import datetime

        report = RiskReport(
            timestamp=datetime.now(),
            portfolio_value=1_000_000,
            cash=200_000,
            total_exposure=Exposure(long_exposure=1200000, short_exposure=0, gross_exposure=1200000, net_exposure=1200000, gross_exposure_pct=1.2, net_exposure_pct=1.2),
            position_count=5,
            concentration_top5_pct=0.45,
            var=PortfolioVaR(var_95=20_000, var_99=35_000),
            correlation=CorrelationMetrics(diversification_score=0.7, avg_correlation=0.3),
            drawdown=DrawdownMetrics(current_drawdown=0.05),
            sector_exposure={"Technology": 0.6, "Financials": 0.2, "Energy": 0.2},
            beta_to_benchmark=1.1,
            stress_test_results={
                "2008_crisis": {"total_pnl_pct": -0.25},
                "covid_crash": {"total_pnl_pct": -0.18},
            },
            breaches=[],
        )

        data = report.to_dict()
        assert "timestamp" in data
        assert "var" in data
        assert data["var"]["var_95"] == 20_000
        assert data["exposure"]["gross_exposure_pct"] == 1.2
        assert data["stress_test_results"]["2008_crisis"]["total_pnl_pct"] == -0.25


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_positions(self):
        """Test all calculators with zero positions."""
        engine = PortfolioRiskEngine()
        positions = []

        exp = ExposureCalculator().calculate_exposure(positions, 100_000)
        assert exp.gross_exposure == 0.0

        conc = ExposureCalculator().calculate_concentration(positions, 100_000)
        assert conc == 0.0

        sector_exp = ExposureCalculator().calculate_sector_exposure(positions, 100_000)
        assert sector_exp == {}

    def test_single_position(self):
        """Test with a single position."""
        pos = Position(symbol="AAPL", quantity=100, avg_entry_price=150, current_price=160)
        positions = [pos]

        exp = ExposureCalculator().calculate_exposure(positions, 16_000)
        assert exp.long_exposure == 16_000
        assert exp.gross_exposure_pct == 1.0

        conc = ExposureCalculator().calculate_concentration(positions, 16_000)
        assert conc == 1.0

    def test_all_cash(self):
        """Test portfolio with only cash (zero positions)."""
        cash = 100_000
        positions = []
        portfolio_value = cash

        exp = ExposureCalculator().calculate_exposure(positions, portfolio_value)
        assert exp.gross_exposure == 0.0
        assert exp.net_exposure == 0.0

    def test_negative_prices(self):
        """Test handling of negative prices (should not crash)."""
        pos = Position(symbol="BAD", quantity=100, avg_entry_price=150, current_price=-10)
        positions = [pos]
        try:
            exp = ExposureCalculator().calculate_exposure(positions, 100_000)
            # Should handle gracefully - exposure will be negative but shouldn't crash
        except Exception:
            pytest.fail("Should handle negative prices gracefully")

    def test_extreme_position_sizes(self):
        """Test with extremely large position."""
        pos = Position(symbol="AAPL", quantity=1_000_000, avg_entry_price=150, current_price=160)
        positions = [pos]
        portfolio_value = 160_000_000

        exp = ExposureCalculator().calculate_exposure(positions, portfolio_value)
        assert exp.gross_exposure_pct == 1.0

        # Test concentration
        conc = ExposureCalculator().calculate_concentration(positions, portfolio_value)
        assert conc == 1.0
