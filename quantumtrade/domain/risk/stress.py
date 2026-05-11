"""
Stress testing scenarios for portfolio risk analysis.

Implements various historical and hypothetical stress scenarios.
"""

from typing import Dict, List, Tuple, Optional
from .models import StressScenario, Position


# Predefined scenarios as specified in requirements
PREDEFINED_SCENARIOS = {
    "2008_financial_crisis": StressScenario(
        name="2008 Financial Crisis",
        description="Global financial crisis with -50% equity decline",
        shocks={"SPY": -0.50, "QQQ": -0.55, "IWM": -0.52, "TLT": 0.25},
        correlation_shock=0.3
    ),
    "2020_covid_crash": StressScenario(
        name="2020 COVID Crash",
        description="Pandemic crash with -34% equity decline",
        shocks={"SPY": -0.34, "QQQ": -0.30, "IWM": -0.35, "TLT": 0.10},
        correlation_shock=0.3
    ),
    "tech_correction_2022": StressScenario(
        name="Tech Correction 2022",
        description="Technology stocks down 35%",
        shocks={"QQQ": -0.35, "XLK": -0.35},
        correlation_shock=0.1
    ),
    "custom_aapl_20pct_drop": StressScenario(
        name="AAPL 20% Drop",
        description="Apple drops 20%",
        shocks={"AAPL": -0.20},
        correlation_shock=0.0
    ),
    "sector_tech_shock": StressScenario(
        name="Tech Sector Shock",
        description="Tech sector stocks drop 30%",
        shocks={"AAPL": -0.30, "MSFT": -0.30, "GOOGL": -0.30, "AMZN": -0.30, "META": -0.30},
        correlation_shock=0.1
    ),
    "rate_shock_100bps": StressScenario(
        name="Rate Shock 100bps",
        description="Interest rates up 100 basis points",
        shocks={"TLT": -0.20, "SPY": -0.10, "QQQ": -0.12},
        correlation_shock=0.1
    ),
}


def apply_scenario(
    portfolio_positions: List[Position],
    scenario: StressScenario,
    position_prices: Dict[str, float],
    sector_mapping: Optional[Dict[str, str]] = None
) -> Dict:
    """Apply scenario to portfolio and return impact results."""
    sector_mapping = sector_mapping or {}
    total_pnl = 0.0
    position_impacts = {}

    for pos in portfolio_positions:
        shock = scenario.shocks.get(pos.symbol, 0.0)
        if pos.symbol not in scenario.shocks:
            sector = sector_mapping.get(pos.symbol)
            if sector and sector in scenario.shocks:
                shock = scenario.shocks[sector]

        impact = pos.market_value * shock
        position_impacts[pos.symbol] = impact
        total_pnl += impact

    portfolio_value = sum(abs(p.market_value) for p in portfolio_positions)
    total_pnl_pct = total_pnl / portfolio_value if portfolio_value > 0 else 0.0

    return {
        "scenario": scenario.name,
        "impact_pct": total_pnl_pct,
        "impact_usd": total_pnl,
        "new_portfolio_value": portfolio_value + total_pnl,
        "position_impacts": position_impacts,
    }


def run_all_scenarios(
    portfolio_positions: List[Position],
    position_prices: Dict[str, float],
    scenarios: Dict[str, StressScenario],
    sector_mapping: Optional[Dict[str, str]] = None
) -> Dict[str, Dict]:
    """Run all stress scenarios against portfolio."""
    results = {}
    for name, scenario in scenarios.items():
        results[name] = apply_scenario(portfolio_positions, scenario, position_prices, sector_mapping)
    return results


def worst_case_scenario(results: Dict[str, Dict]) -> Tuple[str, float]:
    """Find the worst case scenario from results."""
    worst_name = min(results.keys(), key=lambda k: results[k].get("impact_pct", 0))
    return worst_name, results[worst_name].get("impact_pct", 0)


class StressTester:
    """
    Apply stress test scenarios to portfolio positions.

    Scenarios include:
    - 2008 Financial Crisis: -50% equity drop, increased correlations
    - 2020 COVID Crash: -30% drop in one week
    - Custom symbol shocks
    - Sector shocks
    """

    # Predefined scenarios
    SCENARIOS = {
        "2008_crisis": StressScenario(
            name="2008 Financial Crisis",
            description="Global financial crisis with -50% equity decline",
            shocks={"SPY": -0.50, "QQQ": -0.55, "IWM": -0.52, "TLT": 0.25},
            correlation_shock=0.3
        ),
        "covid_crash": StressScenario(
            name="2020 COVID Crash",
            description="Pandemic crash with -30% equity decline in one week",
            shocks={"SPY": -0.30, "QQQ": -0.35, "IWM": -0.32, "TLT": 0.15},
            correlation_shock=0.2
        ),
        "tech_bubble": StressScenario(
            name="Tech Bubble Burst",
            description="Technology sector correction",
            shocks={"AAPL": -0.40, "MSFT": -0.35, "GOOGL": -0.38, "AMZN": -0.45},
            correlation_shock=0.15
        ),
        "energy_crash": StressScenario(
            name="Energy Crisis",
            description="Energy sector shock",
            shocks={"XOM": -0.50, "CVX": -0.45, "SLB": -0.55},
            correlation_shock=0.1
        ),
        "sector_rotation": StressScenario(
            name="Sector Rotation",
            description="Growth to value rotation",
            shocks={
                "XLK": -0.25,  # Tech down
                "XLF": 0.15,   # Financials up
                "XLE": 0.20,   # Energy up
                "XLV": 0.10,   # Healthcare up
            },
            correlation_shock=-0.1
        ),
    }

    def apply_scenario(
        self,
        positions: List[Position],
        scenario: StressScenario,
        sector_map: Dict[str, str]
    ) -> Dict[str, float]:
        """
        Apply stress scenario to positions and calculate P&L impact.

        Args:
            positions: List of Position objects
            scenario: StressScenario to apply
            sector_map: Dict mapping symbol to sector for sector shocks

        Returns:
            Dictionary with impact metrics
        """
        total_pnl = 0.0
        position_impacts: Dict[str, float] = {}

        for pos in positions:
            shock = 0.0

            if pos.symbol in scenario.shocks:
                shock = scenario.shocks[pos.symbol]
            else:
                pos_sector = sector_map.get(pos.symbol, "Unknown")
                if pos_sector in scenario.shocks:
                    shock = scenario.shocks[pos_sector]

            impact = pos.market_value * shock
            position_impacts[pos.symbol] = impact
            total_pnl += impact

        portfolio_value = sum(abs(p.market_value) for p in positions)
        total_pnl_pct = total_pnl / portfolio_value if portfolio_value > 0 else 0.0

        return {
            "scenario": scenario.name,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "position_impacts": position_impacts,
            "portfolio_value": portfolio_value
        }

    def run_all_scenarios(
        self,
        positions: List[Position],
        sector_map: Dict[str, str]
    ) -> Dict[str, Dict[str, float]]:
        """
        Run all predefined stress scenarios.

        Args:
            positions: List of Position objects
            sector_map: Dict mapping symbol to sector

        Returns:
            Dictionary mapping scenario name to results
        """
        results = {}
        for name, scenario in self.SCENARIOS.items():
            results[name] = self.apply_scenario(positions, scenario, sector_map)
        return results

    def create_custom_scenario(
        self,
        name: str,
        description: str,
        shocks: Dict[str, float],
        correlation_shock: float = 0.0
    ) -> StressScenario:
        """
        Create a custom stress scenario.

        Args:
            name: Scenario name
            description: Scenario description
            shocks: Dict mapping symbol/sector to shock percentage
            correlation_shock: Additional correlation in stress

        Returns:
            StressScenario object
        """
        return StressScenario(
            name=name,
            description=description,
            shocks=shocks,
            correlation_shock=correlation_shock
        )

    def apply_custom_shock(
        self,
        positions: List[Position],
        shocks: Dict[str, float],
        sector_map: Dict[str, str] = None
    ) -> Dict[str, float]:
        """
        Apply custom shock dictionary to positions.

        Args:
            positions: List of Position objects
            shocks: Dict mapping symbol/sector to shock percentage
            sector_map: Dict mapping symbol to sector

        Returns:
            Dictionary with impact metrics
        """
        sector_map = sector_map or {}
        scenario = StressScenario(
            name="Custom",
            description="User-defined shock",
            shocks=shocks
        )
        return self.apply_scenario(positions, scenario, sector_map)

    def get_sector_shock(
        self,
        sector: str,
        shock_pct: float
    ) -> StressScenario:
        """
        Create a sector-specific shock scenario.

        Args:
            sector: Sector name to shock
            shock_pct: Shock percentage (-0.30 for 30% drop)

        Returns:
            StressScenario for the sector shock
        """
        return StressScenario(
            name=f"{sector} Shock",
            description=f"{sector} sector drops {shock_pct*100:.0f}%",
            shocks={sector: shock_pct}
        )