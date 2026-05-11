"""
Strategy Plugin Loader - Load and validate custom strategy plugins.

This module provides a plugin system for loading external strategy classes,
validating their interface compliance, and supporting hot-reloading.
"""

import importlib.util
import inspect
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyInterfaceError(Exception):
    """Raised when a strategy does not implement the required interface."""
    pass


class StrategyPluginError(Exception):
    """Raised when there is an error loading a strategy plugin."""
    pass


class StrategyPluginLoader:
    """
    Loads strategy classes from external Python modules with validation.
    
    Features:
    - Loads strategy classes from specified module paths
    - Validates strategy interface compliance (inherits from BaseStrategy)
    - Supports hot-reloading of strategies via file modification tracking
    - Registers strategies in the global registry
    - Provides cross-exchange symbol mapping
    """
    
    REQUIRED_METHODS = [
        'calculate_indicators',
        'generate_signal',
        'get_required_periods',
    ]
    
    def __init__(self, strategies_dir: Optional[str] = None):
        self.strategies_dir = Path(strategies_dir) if strategies_dir else Path("strategy/plugins")
        self._loaded_modules: Dict[str, Any] = {}
        self._module_mtimes: Dict[str, float] = {}
        self._strategy_cache: Dict[str, Any] = {}
        
    def load_strategy_from_module(
        self,
        module_path: str,
        strategy_class_name: Optional[str] = None,
    ) -> Any:
        """
        Load a strategy class from a Python module file.
        
        Args:
            module_path: Path to the Python module (file or dotted path)
            strategy_class_name: Name of the strategy class to load.
                               If None, auto-detects classes inheriting from BaseStrategy
        
        Returns:
            The loaded strategy class
            
        Raises:
            StrategyPluginError: If module cannot be loaded
            StrategyInterfaceError: If strategy does not comply with interface
        """
        module_path = str(module_path)
        
        try:
            if os.path.isfile(module_path):
                spec = importlib.util.spec_from_file_location("plugin_module", module_path)
                if spec is None or spec.loader is None:
                    raise StrategyPluginError(f"Cannot load module from {module_path}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            else:
                module = importlib.import_module(module_path)
        except Exception as e:
            raise StrategyPluginError(f"Failed to load module {module_path}: {e}")
        
        self._loaded_modules[module_path] = module
        
        if strategy_class_name:
            strategy_class = getattr(module, strategy_class_name, None)
            if strategy_class is None:
                raise StrategyPluginError(
                    f"Strategy class '{strategy_class_name}' not found in {module_path}"
                )
            strategy_classes = [strategy_class]
        else:
            strategy_classes = self._find_strategy_classes(module)
            if not strategy_classes:
                raise StrategyPluginError(
                    f"No strategy classes found in {module_path}"
                )
        
        for cls in strategy_classes:
            self._validate_strategy_interface(cls)
        
        return strategy_classes[0]
    
    def _find_strategy_classes(self, module: Any) -> List[Any]:
        """Find all strategy classes in a module that inherit from BaseStrategy."""
        from strategy.base import BaseStrategy
        
        strategy_classes = []
        for name in dir(module):
            obj = getattr(module, name)
            if (
                inspect.isclass(obj) and
                issubclass(obj, BaseStrategy) and
                obj is not BaseStrategy
            ):
                strategy_classes.append(obj)
        return strategy_classes
    
    def _validate_strategy_interface(self, strategy_class: Any) -> None:
        """
        Validate that a strategy class implements the required interface.
        
        Args:
            strategy_class: The strategy class to validate
            
        Raises:
            StrategyInterfaceError: If interface is not properly implemented
        """
        from strategy.base import BaseStrategy
        
        if not inspect.isclass(strategy_class):
            raise StrategyInterfaceError(
                f"{strategy_class} is not a class"
            )
        
        if not issubclass(strategy_class, BaseStrategy):
            raise StrategyInterfaceError(
                f"{strategy_class.__name__} must inherit from BaseStrategy"
            )
        
        for method_name in self.REQUIRED_METHODS:
            if not hasattr(strategy_class, method_name):
                raise StrategyInterfaceError(
                    f"Strategy {strategy_class.__name__} missing required method: {method_name}"
                )
            method = getattr(strategy_class, method_name)
            if not callable(method):
                raise StrategyInterfaceError(
                    f"Strategy {strategy_class.__name__} has non-callable {method_name}"
                )
    
    def load_plugins_from_directory(self, directory: Optional[str] = None) -> Dict[str, Any]:
        """
        Load all strategy plugins from a directory.
        
        Args:
            directory: Directory to scan for plugins. Uses self.strategies_dir if None
            
        Returns:
            Dictionary mapping strategy names to strategy classes
        """
        plugins_dir = Path(directory) if directory else self.strategies_dir
        loaded = {}
        
        if not plugins_dir.exists():
            logger.warning(f"Plugins directory does not exist: {plugins_dir}")
            return loaded
        
        for py_file in plugins_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            
            try:
                strategy_class = self.load_strategy_from_module(str(py_file))
                strategy_name = strategy_class.__name__
                loaded[strategy_name] = strategy_class
                self._strategy_cache[strategy_name] = strategy_class
                logger.info(f"Loaded strategy plugin: {strategy_name}")
            except (StrategyPluginError, StrategyInterfaceError) as e:
                logger.error(f"Failed to load plugin {py_file}: {e}")
        
        return loaded
    
    def register_strategy(
        self,
        name: str,
        strategy_class: Any,
        registry: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a strategy class in the global registry.
        
        Args:
            name: Name to register the strategy under
            strategy_class: The strategy class to register
            registry: Target registry (defaults to global STRATEGY_REGISTRY)
        """
        self._validate_strategy_interface(strategy_class)
        
        if registry is None:
            from strategy import STRATEGY_REGISTRY
            registry = STRATEGY_REGISTRY
        
        registry[name] = strategy_class
        logger.info(f"Registered strategy: {name}")
    
    def hot_reload_strategy(self, module_path: str) -> Optional[Any]:
        """
        Hot-reload a strategy from a module if the file has been modified.
        
        Args:
            module_path: Path to the module file
            
        Returns:
            The reloaded strategy class, or None if no reload needed
        """
        if not os.path.isfile(module_path):
            return None
        
        current_mtime = os.path.getmtime(module_path)
        cached_mtime = self._module_mtimes.get(module_path, 0)
        
        if current_mtime <= cached_mtime:
            return None
        
        self._module_mtimes[module_path] = current_mtime
        strategy_class = self.load_strategy_from_module(module_path)
        
        logger.info(f"Hot-reloaded strategy from {module_path}")
        return strategy_class
    
    def watch_and_reload(
        self,
        callback: Optional[Callable[[str, Any], None]] = None,
    ) -> List[str]:
        """
        Check all loaded plugins for changes and reload if needed.
        
        Args:
            callback: Optional callback called with (name, strategy_class) for each reloaded strategy
            
        Returns:
            List of reloaded strategy names
        """
        reloaded = []
        
        for module_path in list(self._loaded_modules.keys()):
            try:
                strategy_class = self.hot_reload_strategy(module_path)
                if strategy_class:
                    reloaded.append(strategy_class.__name__)
                    if callback:
                        callback(strategy_class.__name__, strategy_class)
            except Exception as e:
                logger.error(f"Error hot-reloading {module_path}: {e}")
        
        return reloaded
    
    def get_cross_exchange_symbol_map(
        self,
        primary_exchange: str,
        target_exchange: str,
    ) -> Dict[str, str]:
        """
        Get symbol mapping between exchanges.
        
        Args:
            primary_exchange: The primary exchange name (e.g., 'binance')
            target_exchange: The target exchange name (e.g., 'coinbase')
            
        Returns:
            Dictionary mapping primary symbols to target symbols
        """
        exchange_mappings = {
            "binance": {
                "coinbase": {
                    "BTCUSDT": "BTC-USD",
                    "ETHUSDT": "ETH-USD",
                    "ADAUSDT": "ADA-USD",
                    "DOGEUSDT": "DOGE-USD",
                    "XRPUSDT": "XRP-USD",
                    "LTCUSDT": "LTC-USD",
                    "LINKUSDT": "LINK-USD",
                    "DOTUSDT": "DOT-USD",
                    "BCHUSDT": "BCH-USD",
                    "ATOMUSDT": "ATOM-USD",
                },
                "kraken": {
                    "BTCUSDT": "XBTUSD",
                    "ETHUSDT": "XETHZUSD",
                    "ADAUSDT": "ADAUSD",
                    "XRPUSDT": "XXRPZUSD",
                    "LTCUSDT": "XLTCZUSD",
                    "DOTUSDT": "DOTUSD",
                },
            },
            "coinbase": {
                "binance": {
                    "BTC-USD": "BTCUSDT",
                    "ETH-USD": "ETHUSDT",
                    "ADA-USD": "ADAUSDT",
                    "DOGE-USD": "DOGEUSDT",
                    "XRP-USD": "XRPUSDT",
                    "LTC-USD": "LTCUSDT",
                    "LINK-USD": "LINKUSDT",
                    "DOT-USD": "DOTUSDT",
                    "BCH-USD": "BCHUSDT",
                    "ATOM-USD": "ATOMUSDT",
                },
            },
        }
        
        return exchange_mappings.get(primary_exchange, {}).get(target_exchange, {})
    
    def map_symbol_for_exchange(
        self,
        symbol: str,
        from_exchange: str,
        to_exchange: str,
    ) -> Optional[str]:
        """
        Map a symbol from one exchange format to another.
        
        Args:
            symbol: The symbol in the source exchange format
            from_exchange: Source exchange name
            to_exchange: Target exchange name
            
        Returns:
            Mapped symbol in target exchange format, or None if no mapping exists
        """
        mapping = self.get_cross_exchange_symbol_map(from_exchange, to_exchange)
        return mapping.get(symbol) or mapping.get(symbol.replace("-", ""))