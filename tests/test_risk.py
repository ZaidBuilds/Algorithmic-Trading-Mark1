"""
Test script for the Risk Management module.

Run this to verify risk management works correctly:
    python test_risk.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from risk.position_sizer import PositionSizer
from risk.stop_loss import StopLossManager
from risk.limits import RiskLimits
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_position_sizer():
    """Test position sizing logic."""
    print("\n" + "="*70)
    print("TEST: Position Sizer")
    print("="*70)
    
    # Create position sizer
    account_balance = 10000.0
    sizer = PositionSizer(
        risk_per_trade=0.02,  # 2% risk per trade
        max_position_pct=0.25,  # Max 25% of account
        account_balance=account_balance
    )
    
    print(f"\n1. Position Sizer: {sizer}")
    print(f"   Account Balance: ${account_balance:,.2f}")
    print(f"   Risk per Trade: {sizer.risk_per_trade*100:.1f}%")
    print(f"   Max Position: {sizer.max_position_pct*100:.1f}%")
    
    # Test 1: Normal position sizing
    print("\n2. Test 1: Normal position sizing")
    entry_price = 100.0
    stop_loss_pct = 0.02  # 2% stop loss
    
    result = sizer.calculate_position_size(entry_price, stop_loss_pct=stop_loss_pct)
    print(f"   Entry Price: ${entry_price:.2f}")
    print(f"   Stop Loss: {stop_loss_pct*100:.1f}% below entry = ${entry_price * (1 - stop_loss_pct):.2f}")
    print(f"   Quantity: {result.quantity:.2f} shares")
    print(f"   Position Value: ${result.position_value:,.2f}")
    print(f"   Risk Amount: ${result.risk_amount:.2f}")
    print(f"   Result: {result.reason}")
    
    assert result.is_valid, "Position size should be valid"
    assert result.quantity > 0, "Quantity should be positive"
    
    # Test 2: Position limited by max position size
    print("\n3. Test 2: Position limited by max size")
    entry_price = 10.0  # Very low price, would require huge position
    result = sizer.calculate_position_size(entry_price, stop_loss_pct=0.01)  # 1% stop loss
    print(f"   Entry Price: ${entry_price:.2f}")
    print(f"   Quantity: {result.quantity:.2f} shares")
    print(f"   Position Value: ${result.position_value:,.2f} (max: ${account_balance * sizer.max_position_pct:,.2f})")
    print(f"   Result: {result.reason}")
    
    assert result.position_value <= account_balance * sizer.max_position_pct, "Position should be limited"
    
    # Test 3: Update balance
    print("\n4. Test 3: Update balance")
    new_balance = 20000.0
    sizer.update_balance(new_balance)
    result = sizer.calculate_position_size(100.0, stop_loss_pct=0.02)
    print(f"   New Balance: ${new_balance:,.2f}")
    print(f"   New Quantity: {result.quantity:.2f} shares (doubled from before)")
    print(f"   New Position Value: ${result.position_value:,.2f}")
    
    print("\n[OK] Position sizer tests passed!")

def test_stop_loss():
    """Test stop-loss management."""
    print("\n" + "="*70)
    print("TEST: Stop Loss Manager")
    print("="*70)
    
    manager = StopLossManager(default_stop_pct=0.02)
    print(f"\n1. Stop Loss Manager: {manager}")
    
    # Test 1: Calculate stop loss
    print("\n2. Test 1: Calculate stop loss")
    entry_price = 100.0
    stop_loss = manager.calculate_stop_loss(entry_price, stop_pct=0.02)
    print(f"   Entry Price: ${entry_price:.2f}")
    print(f"   Stop Loss: ${stop_loss.price:.2f} ({stop_loss.percent*100:.1f}% below entry)")
    
    assert stop_loss.price < entry_price, "Stop loss should be below entry"
    assert stop_loss.percent == 0.02, "Stop loss percent should match"
    
    # Test 2: Check stop loss hit
    print("\n3. Test 2: Check stop loss hit")
    current_price = 97.0  # Below stop loss
    is_hit = manager.check_stop_loss_hit(stop_loss, current_price)
    print(f"   Current Price: ${current_price:.2f}")
    print(f"   Stop Loss Hit: {is_hit}")
    
    assert is_hit, "Stop loss should be hit"
    
    current_price = 99.0  # Above stop loss
    is_hit = manager.check_stop_loss_hit(stop_loss, current_price)
    print(f"   Current Price: ${current_price:.2f}")
    print(f"   Stop Loss Hit: {is_hit}")
    
    assert not is_hit, "Stop loss should not be hit"
    
    # Test 3: Unrealized P&L
    print("\n4. Test 3: Calculate unrealized P&L")
    current_price = 105.0
    quantity = 100.0
    pnl_info = manager.calculate_unrealized_pnl(entry_price, current_price, quantity, stop_loss)
    print(f"   Entry: ${entry_price:.2f}, Current: ${current_price:.2f}, Qty: {quantity:.2f}")
    print(f"   Unrealized P&L: ${pnl_info['unrealized_pnl']:.2f} ({pnl_info['unrealized_pnl_pct']:.2f}%)")
    print(f"   Distance to Stop: ${pnl_info['distance_to_stop']:.2f} ({pnl_info['distance_to_stop_pct']:.2f}%)")
    print(f"   Risk Amount: ${pnl_info['risk_amount']:.2f}")
    
    print("\n[OK] Stop loss manager tests passed!")

def test_risk_limits():
    """Test risk limits."""
    print("\n" + "="*70)
    print("TEST: Risk Limits")
    print("="*70)
    
    initial_balance = 10000.0
    limits = RiskLimits(
        initial_balance=initial_balance,
        max_daily_loss_pct=0.05,  # 5% max daily loss
        max_position_pct=0.25,  # 25% max position
        max_open_positions=3,
        max_drawdown_pct=0.20  # 20% max drawdown
    )
    
    print(f"\n1. Risk Limits: {limits}")
    print(f"   Initial Balance: ${initial_balance:,.2f}")
    
    # Test 1: Position size limit
    print("\n2. Test 1: Position size limit")
    position_value = 3000.0  # 30% of account
    result = limits.check_position_size_limit(position_value)
    print(f"   Position Value: ${position_value:,.2f}")
    print(f"   Max Allowed: ${limits.current_balance * limits.max_position_pct:,.2f}")
    print(f"   Allowed: {result.is_allowed}, Reason: {result.reason}")
    
    assert not result.is_allowed, "Position should exceed limit"
    
    position_value = 2000.0  # 20% of account
    result = limits.check_position_size_limit(position_value)
    print(f"   Position Value: ${position_value:,.2f}")
    print(f"   Allowed: {result.is_allowed}")
    
    assert result.is_allowed, "Position should be within limit"
    
    # Test 2: Daily loss limit
    print("\n3. Test 2: Daily loss limit")
    from datetime import date
    today = date.today()
    
    # Simulate daily loss
    limits.update_balance(9500.0, today)  # 5% loss
    result = limits.check_daily_loss_limit()
    print(f"   Balance: ${limits.current_balance:,.2f}")
    print(f"   Daily P&L: ${limits.daily_pnl:,.2f}")
    print(f"   Allowed: {result.is_allowed}, Reason: {result.reason}")
    
    limits.update_balance(9400.0, today)  # 6% loss
    result = limits.check_daily_loss_limit()
    print(f"   Balance: ${limits.current_balance:,.2f}")
    print(f"   Daily P&L: ${limits.daily_pnl:,.2f}")
    print(f"   Allowed: {result.is_allowed}, Reason: {result.reason}")
    
    assert not result.is_allowed, "Should exceed daily loss limit"
    
    # Test 3: Max drawdown
    print("\n4. Test 3: Max drawdown")
    limits.peak_balance = 12000.0  # Peak was higher
    limits.current_balance = 9500.0  # Now at 9500
    result = limits.check_max_drawdown()
    print(f"   Peak Balance: ${limits.peak_balance:,.2f}")
    print(f"   Current Balance: ${limits.current_balance:,.2f}")
    print(f"   Drawdown: ${limits.peak_balance - limits.current_balance:,.2f}")
    print(f"   Allowed: {result.is_allowed}, Reason: {result.reason}")
    
    # Test 4: Status
    print("\n5. Test 4: Get status")
    status = limits.get_status()
    print(f"   Current Balance: ${status['current_balance']:,.2f}")
    print(f"   Peak Balance: ${status['peak_balance']:,.2f}")
    print(f"   Current Drawdown: ${status['current_drawdown']:,.2f} ({status['current_drawdown_pct']:.2f}%)")
    
    print("\n[OK] Risk limits tests passed!")

if __name__ == "__main__":
    print("="*70)
    print("RISK MANAGEMENT TEST SUITE")
    print("="*70)
    
    try:
        test_position_sizer()
        test_stop_loss()
        test_risk_limits()
        
        print("\n" + "="*70)
        print("[OK] All risk management tests passed!")
        print("="*70)
    
    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

