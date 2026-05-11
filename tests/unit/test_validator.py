"""Tests for model validator and canary deployment."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from quantumtrade.mlops.validator import (
    ModelValidator,
    ValidationResult,
    PromotionCriteria,
    CanaryDeployer,
    ValidationStatus,
)


class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_create_result(self):
        """Test creating validation result."""
        result = ValidationResult(status=ValidationStatus.PASSED)
        assert result.status == ValidationStatus.PASSED
        assert len(result.checks) == 0
        assert result.is_passing() is True
    
    def test_add_check_pass(self):
        """Test adding passing check."""
        result = ValidationResult(status=ValidationStatus.PASSED)
        result.add_check("min_accuracy", True)
        assert result.checks["min_accuracy"] is True
        assert result.is_passing() is True
    
    def test_add_check_fail(self):
        """Test adding failing check."""
        result = ValidationResult(status=ValidationStatus.PASSED)
        result.add_check("min_accuracy", False, "Too low")
        assert result.checks["min_accuracy"] is False
        assert len(result.errors) == 1
        assert result.is_passing() is False
    
    def test_add_warning(self):
        """Test adding warning."""
        result = ValidationResult(status=ValidationStatus.PASSED)
        result.add_warning("low_data", "Only 500 samples")
        assert len(result.warnings) == 1
        # Warning doesn't fail
        assert result.is_passing() is True
    
    def test_to_dict(self):
        """Test serialization."""
        result = ValidationResult(status=ValidationStatus.FAILED)
        result.add_check("test", False, "error")
        d = result.to_dict()
        assert d["status"] == "failed"
        assert "test" in d["checks"]


class TestModelValidator:
    """Test ModelValidator."""
    
    @pytest.fixture
    def validator(self):
        """Create validator with default criteria."""
        criteria = PromotionCriteria(
            min_accuracy=0.70,
            min_precision=0.65,
            min_recall=0.65,
            max_accuracy_drop=0.02,
            requires_canary_pass=False,
        )
        return ModelValidator(criteria=criteria)
    
    def test_validator_init(self, validator):
        """Test initialization."""
        assert validator.criteria.min_accuracy == 0.70
        assert len(validator.validation_history) == 0
    
    def test_validate_absolute_thresholds_pass(self, validator):
        """Test absolute metric thresholds pass."""
        candidate = {
            "accuracy": 0.75,
            "precision": 0.70,
            "recall": 0.68,
            "f1": 0.69,
        }
        baseline = None
        backtest = None
        stress = None
        
        result = validator.validate(candidate, baseline, backtest, stress)
        assert result.status == ValidationStatus.PASSED
        assert len(result.errors) == 0
    
    def test_validate_absolute_thresholds_fail(self, validator):
        """Test absolute threshold failure."""
        candidate = {
            "accuracy": 0.60,  # below 0.70
            "precision": 0.70,
            "recall": 0.68,
            "f1": 0.69,
        }
        
        result = validator.validate(candidate)
        assert result.status == ValidationStatus.FAILED
        assert "min_accuracy" in result.checks
        assert result.checks["min_accuracy"] is False
    
    def test_validate_improvement_check(self, validator):
        """Test improvement over baseline."""
        candidate = {"accuracy": 0.80}
        baseline = {"accuracy": 0.78}
        
        result = validator.validate(candidate, baseline)
        assert result.status == ValidationStatus.PASSED
        assert "improvement_vs_baseline" in result.checks
    
    def test_improvement_threshold_too_small(self, validator):
        """Test improvement below threshold."""
        validator.criteria.max_accuracy_drop = 0.01  # Strict
        
        candidate = {"accuracy": 0.78}
        baseline = {"accuracy": 0.80}  # 2.5% drop
        
        result = validator.validate(candidate, baseline)
        assert result.status == ValidationStatus.FAILED
    
    def test_backtest_validation_pass(self):
        """Test backtest validation - all good."""
        validator = ModelValidator(PromotionCriteria(
            min_sharpe_ratio=1.0,
            max_drawdown=0.30,
            min_trades=50,
        ))
        
        backtest = {
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.15,
            "num_trades": 150,
            "win_rate": 0.55,
        }
        
        candidate = {"accuracy": 0.75}
        result = validator.validate(candidate, backtest_results=backtest)
        assert result.status == ValidationStatus.PASSED
    
    def test_backtest_validation_fail(self):
        """Test backtest validation failure."""
        validator = ModelValidator(PromotionCriteria(
            min_sharpe_ratio=2.0,
            max_drawdown=0.10,
            min_trades=200,
        ))
        
        backtest = {
            "sharpe_ratio": 1.5,  # below 2.0
            "max_drawdown": 0.05,  # OK
            "num_trades": 150,     # below 200
        }
        
        result = validator.validate({"accuracy": 0.75}, backtest_results=backtest)
        assert result.status == ValidationStatus.FAILED
        assert len(result.errors) >= 2
    
    def test_stress_test_validation(self):
        """Test stress test validation."""
        validator = ModelValidator(PromotionCriteria())
        
        stress = {"accuracy_degradation_pct": 25.0}  # >20%
        result = validator.validate({"accuracy": 0.7}, stress_results=stress)
        assert result.status == ValidationStatus.FAILED
        
        stress_ok = {"accuracy_degradation_pct": 15.0}
        result_ok = validator.validate({"accuracy": 0.7}, stress_results=stress_ok)
        assert result_ok.status == ValidationStatus.PASSED
    
    def test_requires_canary(self):
        """Test canary requirement check."""
        criteria_with_canary = PromotionCriteria(requires_canary_pass=True)
        criteria_without = PromotionCriteria(requires_canary_pass=False)
        
        validator_with = ModelValidator(criteria_with_canary)
        validator_without = ModelValidator(criteria_without)
        
        assert validator_with.requires_canary() is True
        assert validator_without.requires_canary() is False
    
    def test_get_canary_config(self):
        """Test retrieving canary configuration."""
        criteria = PromotionCriteria(
            canary_capital_pct=0.02,
            canary_duration_hours=48,
        )
        validator = ModelValidator(criteria)
        capital, duration = validator.get_canary_config()
        assert capital == 0.02
        assert duration == 48


class TestCanaryDeployer:
    """Test CanaryDeployer."""
    
    @pytest.fixture
    def deployer(self):
        """Create canary deployer."""
        return CanaryDeployer(initial_capital=100000.0)
    
    def test_init(self, deployer):
        """Test initialization."""
        assert deployer.initial_capital == 100000.0
        assert deployer.current_phase == 0
        assert deployer.rollback_triggered is False
    
    def test_start_deployment(self, deployer):
        """Test starting canary."""
        deployer.start_deployment("v2.0")
        assert deployer.current_model_version == "v2.0"
        assert deployer.phase_start_time is not None
        assert deployer.current_phase == 0
    
    def test_get_allocation_phase1(self, deployer):
        """Test phase 1 allocation (1%)."""
        deployer.start_deployment("v1")
        allocation = deployer.get_allocation()
        assert allocation == 0.01
    
    def test_get_allocation_progression(self, deployer):
        """Test allocation increases over time."""
        deployer.start_deployment("v1")
        
        # Phase 1: 1%
        alloc1 = deployer.get_allocation()
        assert alloc1 == 0.01
        
        # Simulate phase 1 completion
        deployer.phase_start_time = datetime.utcnow() - timedelta(hours=25)
        alloc2 = deployer.get_allocation()
        assert alloc2 == 0.05  # Phase 2
    
    def test_should_rollback(self, deployer):
        """Test rollback trigger."""
        deployer.start_deployment("v1")
        
        baseline = {"accuracy": 0.85}
        current = {"accuracy": 0.78}  # ~8% drop
        
        should = deployer.should_rollback(current, baseline, threshold=0.05)
        assert should is True
        assert deployer.rollback_triggered is True
    
    def test_no_rollback_above_threshold(self, deployer):
        """Test no rollback within threshold."""
        deployer.start_deployment("v1")
        
        baseline = {"accuracy": 0.85}
        current = {"accuracy": 0.82}  # ~3.5% drop < 5%
        
        should = deployer.should_rollback(current, baseline, threshold=0.05)
        assert should is False
    
    def test_is_complete(self, deployer):
        """Test canary completion."""
        deployer.start_deployment("v1")
        assert deployer.is_complete() is False
        
        # Advance through all phases
        deployer.phase_start_time = datetime.utcnow() - timedelta(days=30)
        assert deployer.is_complete() is True
    
    def test_get_status(self, deployer):
        """Test status reporting."""
        deployer.start_deployment("v1")
        status = deployer.get_status()
        
        assert "status" in status
        assert status["model_version"] == "v1"
        assert "allocation_pct" in status
        assert status["phase"] == 1
