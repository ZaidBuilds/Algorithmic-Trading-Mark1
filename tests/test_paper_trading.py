"""
Test script for Paper Trading module.

Run this to verify paper trading works correctly:
    python test_paper_trading.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from execution.paper_trader import PaperTrader
from execution.order import OrderSide, OrderType
from risk.position_sizer import PositionSizer
from risk.stop_loss import StopLossManager
from risk.limits import RiskLimits
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_paper_trader_basic():
    """Test basic paper trading functionality."""
    print("\n" + "="*70)
    print("TEST: Paper Trader - Basic Functionality")
    print("="*70)
    
    # Create paper trader
    initial_balance = 10000.0
    trader = PaperTrader(initial_balance=initial_balance, commission=0.001)
    print(f"\n1. Created Paper Trader: {trader}")
    print(f"   Initial Balance: ${initial_balance:,.2f}")
    
    # Test 1: Submit and execute BUY order
    print("\n2. Test 1: Submit and execute BUY order")
    order = trader.submit_order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=10.0,
        order_type=OrderType.MARKET
    )
    
    current_price = 150.0
    filled = trader.execute_order(order, current_price)
    
    print(f"   Order: {order}")
    print(f"   Filled: {filled}")
    print(f"   Fill Price: ${order.filled_price:.2f}")
    print(f"   Commission: ${order.commission:.2f}")
    print(f"   Cash Balance: ${trader.get_balance():,.2f}")
    
    assert filled, "Order should be filled"
    assert order.is_filled(), "Order status should be FILLED"
    
    # Check position
    position = trader.get_position("AAPL")
    assert position is not None, "Position should exist"
    print(f"   Position: {position.quantity:.2f} shares @ ${position.entry_price:.2f}")
    
    # Test 2: Update position price
    print("\n3. Test 2: Update position price")
    trader.update_position_price("AAPL", 155.0)
    position = trader.get_position("AAPL")
    print(f"   Current Price: ${position.current_price:.2f}")
    print(f"   Unrealized P&L: ${position.unrealized_pnl:.2f} ({position.unrealized_pnl_pct:.2f}%)")
    
    # Test 3: Submit and execute SELL order
    print("\n4. Test 3: Submit and execute SELL order")
    sell_order = trader.submit_order(
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=10.0,
        order_type=OrderType.MARKET
    )
    
    exit_price = 155.0
    filled = trader.execute_order(sell_order, exit_price)
    
    print(f"   Order: {sell_order}")
    print(f"   Filled: {filled}")
    print(f"   Exit Price: ${exit_price:.2f}")
    print(f"   Cash Balance: ${trader.get_balance():,.2f}")
    
    # Check trade history
    assert len(trader.trades) == 1, "Should have 1 completed trade"
    trade = trader.trades[0]
    print(f"   Trade P&L: ${trade.pnl:.2f} ({trade.pnl_pct:.2f}%)")
    print(f"   Duration: {trade.duration_days} days")
    
    # Test 4: Get summary
    print("\n5. Test 4: Get summary")
    summary = trader.get_summary()
    print(f"   Total Equity: ${summary['total_equity']:,.2f}")
    print(f"   Total P&L: ${summary['total_pnl']:,.2f} ({summary['total_pnl_pct']:.2f}%)")
    print(f"   Realized P&L: ${summary['realized_pnl']:,.2f}")
    print(f"   Number of Trades: {summary['num_trades']}")
    
    print("\n[OK] Basic paper trading tests passed!")

def test_paper_trader_with_risk_management():
    """Test paper trading with risk management integration."""
    print("\n" + "="*70)
    print("TEST: Paper Trader - Risk Management Integration")
    print("="*70)
    
    # Create components
    initial_balance = 10000.0
    trader = PaperTrader(initial_balance=initial_balance)
    
    position_sizer = PositionSizer(
        risk_per_trade=0.02,  # 2% risk
        max_position_pct=0.25,  # 25% max position
        account_balance=initial_balance
    )
    
    stop_loss_manager = StopLossManager(default_stop_pct=0.02)
    
    risk_limits = RiskLimits(
        initial_balance=initial_balance,
        max_daily_loss_pct=0.05,
        max_position_pct=0.25,
        max_open_positions=3
    )
    
    # Set risk management
    trader.set_position_sizer(position_sizer)
    trader.set_stop_loss_manager(stop_loss_manager)
    trader.set_risk_limits(risk_limits)
    
    print(f"\n1. Setup: {trader}")
    print(f"   Position Sizer: {position_sizer}")
    print(f"   Stop Loss Manager: {stop_loss_manager}")
    print(f"   Risk Limits: {risk_limits}")
    
    # Test: Use position sizer to calculate size
    print("\n2. Test: Position sizing")
    entry_price = 100.0
    result = position_sizer.calculate_position_size(entry_price, stop_loss_pct=0.02)
    
    print(f"   Entry Price: ${entry_price:.2f}")
    print(f"   Calculated Quantity: {result.quantity:.2f} shares")
    print(f"   Position Value: ${result.position_value:,.2f}")
    print(f"   Risk Amount: ${result.risk_amount:.2f}")
    
    # Execute order with calculated size
    order = trader.submit_order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=result.quantity,
        order_type=OrderType.MARKET
    )
    
    trader.execute_order(order, entry_price)
    
    # Set stop loss
    position = trader.get_position("AAPL")
    if position and stop_loss_manager:
        stop_loss = stop_loss_manager.calculate_stop_loss(entry_price, stop_pct=0.02)
        position.stop_loss_price = stop_loss.price
        print(f"   Stop Loss Set: ${stop_loss.price:.2f}")
    
    # Test stop loss trigger
    print("\n3. Test: Stop loss trigger")
    current_price = 97.0  # Below stop loss
    trader.update_position_price("AAPL", current_price)
    
    hit_symbols = trader.check_stop_losses({"AAPL": current_price})
    print(f"   Stop Loss Hit: {len(hit_symbols) > 0}")
    
    if hit_symbols:
        print(f"   Position closed due to stop loss")
        assert "AAPL" not in trader.positions, "Position should be closed"
    
    print("\n[OK] Risk management integration tests passed!")

if __name__ == "__main__":
    print("="*70)
    print("PAPER TRADING TEST SUITE")
    print("="*70)
    
    try:
        test_paper_trader_basic()
        test_paper_trader_with_risk_management()
        
        print("\n" + "="*70)
        print("[OK] All paper trading tests passed!")
        print("="*70)
    
    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

