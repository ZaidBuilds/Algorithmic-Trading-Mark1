"""
QuantumTrade Dashboard - Professional Desktop UI
A comprehensive PyQt5 application for managing backtests, strategies, and results.
"""

import sys
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List

import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QDateEdit, QSpinBox,
    QDoubleSpinBox, QCheckBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QProgressBar, QMessageBox, QFileDialog, QStatusBar, QSplitter,
    QListWidget, QListWidgetItem, QDialog, QFormLayout
)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QIcon, QPixmap, QPainter
from PyQt5.QtChart import QChart, QChartView, QLineSeries
from PyQt5.QtCore import QPointF

# Import trading components
from config.settings import settings
from data.loader import load_yahoo
from strategy.ema_crossover import EMACrossoverStrategy
from strategy.sma_strategy import SMAStrategy
from strategy.rsi_strategy import RSIStrategy
from strategy.macd_strategy import MACDStrategy
from strategy.bollinger_strategy import BollingerBandsStrategy
from quantumtrade.backtesting.engine import BacktestEngine
from quantumtrade.backtesting.metrics import BacktestMetrics
from quantumtrade.backtesting.reporter import BacktestReporter
from execution.broker_client import PaperBroker
from risk.risk_manager import RiskManager
from utils.logger import setup_logger

# Initialize logger first
logger = setup_logger("Dashboard", level="INFO")

# Import ML & AI components
ML_AI_AVAILABLE = True
try:
    from quantumtrade.core.decision_engine import UnifiedDecisionEngine
    from ml.feature_engineer import FeatureEngineer
    from ml.ml_predictor import MLPredictor
    from ai.ollama_advisor import OllamaAdvisor
except ImportError as e:
    logger.warning(f"ML/AI components not fully available: {e}")
    ML_AI_AVAILABLE = False

# Strategy registry
STRATEGIES = {
    "EMA Crossover": EMACrossoverStrategy,
    "SMA Crossover": SMAStrategy,
    "RSI Strategy": RSIStrategy,
    "MACD Strategy": MACDStrategy,
    "Bollinger Bands": BollingerBandsStrategy,
}

SYMBOLS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "META", "NVDA", "AMD"]
TIMEFRAMES = ["1d", "1h", "15m", "5m"]


class BacktestWorker(QThread):
    """Worker thread for running backtests without blocking UI"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, symbol: str, strategy_name: str, capital: float,
                 start_date: str, end_date: str, timeframe: str = "1d"):
        super().__init__()
        self.symbol = symbol
        self.strategy_name = strategy_name
        self.capital = capital
        self.start_date = start_date
        self.end_date = end_date
        self.timeframe = timeframe

    def run(self):
        try:
            self.progress.emit(f"Loading historical data for {self.symbol}...")
            
            # Load data
            data = load_yahoo(
                symbol=self.symbol,
                start_date=self.start_date,
                end_date=self.end_date,
                interval=self.timeframe
            )
            
            if data is None or len(data) == 0:
                self.error.emit(f"No data found for {self.symbol}")
                return

            self.progress.emit(f"Loaded {len(data)} candles")
            self.progress.emit(f"Running {self.strategy_name} strategy...")

            # Initialize strategy
            strategy_class = STRATEGIES.get(self.strategy_name)
            if not strategy_class:
                self.error.emit(f"Unknown strategy: {self.strategy_name}")
                return

            strategy = strategy_class()

            # Run backtest
            broker = PaperBroker(initial_capital=self.capital)
            risk_manager = RiskManager(settings)
            engine = BacktestEngine(
                data=data,
                strategy=strategy,
                broker=broker,
                risk_manager=risk_manager
            )

            self.progress.emit("Running backtest engine...")
            metrics = engine.run()

            self.progress.emit("Calculating metrics...")
            
            # Prepare results
            results = {
                "symbol": self.symbol,
                "strategy": self.strategy_name,
                "capital": self.capital,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "timeframe": self.timeframe,
                "metrics": {
                    "initial_balance": metrics.initial_balance,
                    "final_balance": metrics.final_balance,
                    "total_return": metrics.total_return,
                    "total_return_pct": metrics.total_return_pct,
                    "total_trades": metrics.total_trades,
                    "winning_trades": metrics.winning_trades,
                    "losing_trades": metrics.losing_trades,
                    "win_rate": metrics.win_rate,
                    "profit_factor": metrics.profit_factor,
                    "avg_win": metrics.avg_win,
                    "avg_loss": metrics.avg_loss,
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "max_drawdown": metrics.max_drawdown,
                    "max_drawdown_pct": metrics.max_drawdown_pct,
                },
                "trades": [
                    {
                        "entry_date": str(t.entry_date),
                        "exit_date": str(t.exit_date),
                        "entry_price": float(t.entry_price),
                        "exit_price": float(t.exit_price),
                        "quantity": float(t.quantity),
                        "pnl": float(t.pnl),
                        "pnl_pct": float(t.pnl_pct),
                    }
                    for t in metrics.trades
                ],
                "equity_curve": [float(e) for e in metrics.equity_curve],
            }

            # Optional: Add ML/AI analysis
            if ML_AI_AVAILABLE:
                try:
                    self.progress.emit("Analyzing with ML/AI...")
                    decision_engine = UnifiedDecisionEngine(use_ai=False)  # AI requires Ollama
                    
                    # Get last signal from decision engine
                    analysis = decision_engine.process_price_data(data)
                    
                    results["ml_ai"] = {
                        "timestamp": str(analysis.get('timestamp')),
                        "price": analysis.get('price'),
                        "technical": analysis.get('technical', {}),
                        "ml": analysis.get('ml'),
                        "ai": analysis.get('ai'),
                    }
                except Exception as e:
                    logger.warning(f"ML/AI analysis failed: {e}")

            self.progress.emit("✓ Backtest completed successfully!")
            self.finished.emit(results)

        except Exception as e:
            logger.error(f"Backtest error: {e}")
            self.error.emit(f"Backtest error: {str(e)}")


class ConfigDialog(QDialog):
    """Configuration settings dialog"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration Settings")
        self.setGeometry(100, 100, 400, 300)
        
        layout = QFormLayout()
        
        # Initial capital
        self.capital_input = QDoubleSpinBox()
        self.capital_input.setMinimum(1000)
        self.capital_input.setMaximum(10000000)
        self.capital_input.setValue(settings.INITIAL_CAPITAL)
        layout.addRow("Initial Capital ($):", self.capital_input)
        
        # Commission
        self.commission_input = QDoubleSpinBox()
        self.commission_input.setMinimum(0)
        self.commission_input.setMaximum(1)
        self.commission_input.setValue(settings.COMMISSION_PCT * 100)
        self.commission_input.setSingleStep(0.001)
        layout.addRow("Commission (%):", self.commission_input)
        
        # Max position size
        self.position_size_input = QDoubleSpinBox()
        self.position_size_input.setMinimum(0)
        self.position_size_input.setMaximum(100)
        self.position_size_input.setValue(settings.MAX_POSITION_SIZE_PCT * 100)
        layout.addRow("Max Position Size (%):", self.position_size_input)
        
        # Save button
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self.accept)
        layout.addRow(save_btn)
        
        self.setLayout(layout)


class QuantumTradeDashboard(QMainWindow):
    """Main dashboard application"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("QuantumTrade Dashboard - Investment Management System")
        self.setGeometry(0, 0, 1400, 900)
        self.backtest_results = {}
        self.current_metrics = None
        
        # Setup UI
        self.setup_ui()
        self.load_recent_results()
        
        logger.info("Dashboard started")

    def setup_ui(self):
        """Setup main UI components"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()

        # Header
        header = self.create_header()
        main_layout.addLayout(header)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self.create_backtest_tab(), "📊 Backtest")
        tabs.addTab(self.create_results_tab(), "📈 Results")
        tabs.addTab(self.create_comparison_tab(), "⚖️ Compare")
        tabs.addTab(self.create_archive_tab(), "📁 Archive")
        tabs.addTab(self.create_settings_tab(), "⚙️ Settings")
        
        main_layout.addWidget(tabs)

        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

        main_widget.setLayout(main_layout)

    def create_header(self):
        """Create header with logo and title"""
        layout = QHBoxLayout()
        
        title = QLabel("QuantumTrade Dashboard")
        title_font = QFont("Arial", 18, QFont.Bold)
        title.setFont(title_font)
        
        subtitle = QLabel("Professional Trading System Management")
        subtitle_font = QFont("Arial", 10)
        subtitle_font.setItalic(True)
        subtitle.setFont(subtitle_font)
        subtitle.setStyleSheet("color: gray;")
        
        version = QLabel("v1.0.0 | Feb 21, 2026")
        version.setStyleSheet("color: #666; font-size: 9pt;")
        
        layout.addWidget(title, 1)
        layout.addStretch()
        layout.addWidget(version)
        
        return layout

    def create_backtest_tab(self):
        """Create backtest execution tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Input section
        input_layout = QHBoxLayout()
        
        # Symbol selection
        input_layout.addWidget(QLabel("Symbol:"))
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(SYMBOLS)
        input_layout.addWidget(self.symbol_combo)

        # Strategy selection
        input_layout.addWidget(QLabel("Strategy:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(STRATEGIES.keys())
        input_layout.addWidget(self.strategy_combo)

        # Timeframe
        input_layout.addWidget(QLabel("Timeframe:"))
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(TIMEFRAMES)
        input_layout.addWidget(self.timeframe_combo)

        input_layout.addStretch()
        layout.addLayout(input_layout)

        # Configuration section
        config_layout = QHBoxLayout()
        
        # Capital
        config_layout.addWidget(QLabel("Capital ($):"))
        self.capital_spin = QDoubleSpinBox()
        self.capital_spin.setMinimum(1000)
        self.capital_spin.setMaximum(10000000)
        self.capital_spin.setValue(100000)
        self.capital_spin.setSingleStep(10000)
        config_layout.addWidget(self.capital_spin)

        # Start date
        config_layout.addWidget(QLabel("Start Date:"))
        self.start_date = QDateEdit()
        self.start_date.setDate(QDate(2023, 1, 1))
        config_layout.addWidget(self.start_date)

        # End date
        config_layout.addWidget(QLabel("End Date:"))
        self.end_date = QDateEdit()
        self.end_date.setDate(QDate.currentDate())
        config_layout.addWidget(self.end_date)

        config_layout.addStretch()
        layout.addLayout(config_layout)

        # Run button
        run_layout = QHBoxLayout()
        self.run_btn = QPushButton("🚀 RUN BACKTEST")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.run_btn.clicked.connect(self.run_backtest)
        run_layout.addStretch()
        run_layout.addWidget(self.run_btn)
        run_layout.addStretch()
        layout.addLayout(run_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status message
        self.status_label = QLabel("Ready to run backtest")
        layout.addWidget(self.status_label)

        # Results display (trading summary)
        layout.addWidget(QLabel("Trading Summary:"))
        self.results_table = QTableWidget(10, 2)
        self.results_table.setColumnWidth(0, 200)
        self.results_table.setColumnWidth(1, 200)
        self.results_table.setHorizontalHeaderLabels(["Metric", "Value"])
        layout.addWidget(self.results_table)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_results_tab(self):
        """Create results visualization tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Backtest Results & Analysis"))

        # Chart area
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        layout.addWidget(self.chart_view)

        # Trades table
        layout.addWidget(QLabel("Executed Trades:"))
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(7)
        self.trades_table.setHorizontalHeaderLabels([
            "Entry Date", "Exit Date", "Entry", "Exit", "Qty", "P&L", "P&L %"
        ])
        layout.addWidget(self.trades_table)

        widget.setLayout(layout)
        return widget

    def create_comparison_tab(self):
        """Create strategy comparison tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Selection
        select_layout = QHBoxLayout()
        select_layout.addWidget(QLabel("Select Strategies to Compare:"))
        
        self.compare_ema_check = QCheckBox("EMA Crossover")
        self.compare_sma_check = QCheckBox("SMA Crossover")
        self.compare_rsi_check = QCheckBox("RSI Strategy")
        self.compare_macd_check = QCheckBox("MACD Strategy")
        self.compare_bollinger_check = QCheckBox("Bollinger Bands")
        
        select_layout.addWidget(self.compare_ema_check)
        select_layout.addWidget(self.compare_sma_check)
        select_layout.addWidget(self.compare_rsi_check)
        select_layout.addWidget(self.compare_macd_check)
        select_layout.addWidget(self.compare_bollinger_check)
        select_layout.addStretch()
        
        layout.addLayout(select_layout)

        # Comparison button
        compare_btn = QPushButton("Compare Selected Strategies")
        compare_btn.clicked.connect(self.compare_strategies)
        layout.addWidget(compare_btn)

        # Comparison table
        self.comparison_table = QTableWidget()
        self.comparison_table.setColumnCount(8)
        self.comparison_table.setHorizontalHeaderLabels([
            "Strategy", "Total Return %", "Win Rate %", "Sharpe Ratio",
            "Max Drawdown %", "Total Trades", "Avg P&L", "Profit Factor"
        ])
        layout.addWidget(self.comparison_table)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_archive_tab(self):
        """Create results archive tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Historical Backtest Results"))

        # Results list
        self.archive_list = QListWidget()
        layout.addWidget(self.archive_list)

        # Buttons
        btn_layout = QHBoxLayout()
        view_btn = QPushButton("👁️ View Details")
        view_btn.clicked.connect(self.view_archive_details)
        export_btn = QPushButton("📥 Export to CSV")
        export_btn.clicked.connect(self.export_archive)
        delete_btn = QPushButton("🗑️ Delete")
        delete_btn.clicked.connect(self.delete_archive)
        
        btn_layout.addWidget(view_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(delete_btn)
        layout.addLayout(btn_layout)

        widget.setLayout(layout)
        return widget

    def create_settings_tab(self):
        """Create settings tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("System Configuration"))

        # Settings form
        form_layout = QFormLayout()

        # Initial capital
        capital_spin = QDoubleSpinBox()
        capital_spin.setMinimum(1000)
        capital_spin.setMaximum(10000000)
        capital_spin.setValue(settings.INITIAL_CAPITAL)
        capital_spin.setSingleStep(10000)
        form_layout.addRow("Initial Capital ($):", capital_spin)

        # Commission
        commission_spin = QDoubleSpinBox()
        commission_spin.setMinimum(0)
        commission_spin.setMaximum(1)
        commission_spin.setValue(settings.COMMISSION_PCT * 100)
        commission_spin.setSingleStep(0.001)
        form_layout.addRow("Commission (%):", commission_spin)

        # Max position size
        pos_size_spin = QDoubleSpinBox()
        pos_size_spin.setMinimum(0)
        pos_size_spin.setMaximum(100)
        pos_size_spin.setValue(settings.MAX_POSITION_SIZE_PCT * 100)
        form_layout.addRow("Max Position Size (%):", pos_size_spin)

        # Max daily loss
        daily_loss_spin = QDoubleSpinBox()
        daily_loss_spin.setMinimum(0)
        daily_loss_spin.setMaximum(100)
        daily_loss_spin.setValue(5.0)
        form_layout.addRow("Max Daily Loss (%):", daily_loss_spin)

        layout.addLayout(form_layout)

        # Save button
        save_btn = QPushButton("💾 Save Settings")
        save_btn.clicked.connect(lambda: self.statusBar.showMessage("Settings saved"))
        layout.addWidget(save_btn)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def run_backtest(self):
        """Run backtest in worker thread"""
        symbol = self.symbol_combo.currentText()
        strategy = self.strategy_combo.currentText()
        capital = self.capital_spin.value()
        timeframe = self.timeframe_combo.currentText()
        start_date = self.start_date.date().toString("yyyy-MM-dd")
        end_date = self.end_date.date().toString("yyyy-MM-dd")

        self.run_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Backtest running...")

        self.worker = BacktestWorker(symbol, strategy, capital, start_date, end_date, timeframe)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.backtest_finished)
        self.worker.error.connect(self.backtest_error)
        self.worker.start()

    def update_progress(self, message: str):
        """Update progress display"""
        self.status_label.setText(message)
        self.progress_bar.setValue(min(self.progress_bar.value() + 10, 100))

    def backtest_finished(self, results: dict):
        """Handle completed backtest"""
        self.backtest_results = results
        self.current_metrics = results["metrics"]

        # Update results table
        self.display_results()

        # Update trades table
        self.display_trades(results["trades"])

        # Update chart
        self.display_equity_chart(results["equity_curve"])

        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(100)
        self.run_btn.setEnabled(True)
        self.statusBar.showMessage("✓ Backtest completed successfully")
        
        # Save results
        self.save_results(results)

        QMessageBox.information(self, "Success", "Backtest completed successfully!")

    def backtest_error(self, error: str):
        """Handle backtest error"""
        self.progress_bar.setVisible(False)
        self.run_btn.setEnabled(True)
        self.status_label.setText(f"Error: {error}")
        self.statusBar.showMessage("Backtest failed")
        QMessageBox.critical(self, "Error", f"Backtest failed:\n{error}")

    def display_results(self):
        """Display backtest results in table"""
        if not self.current_metrics:
            return

        metrics = self.current_metrics
        data = [
            ("Initial Balance", f"${metrics['initial_balance']:,.2f}"),
            ("Final Balance", f"${metrics['final_balance']:,.2f}"),
            ("Total Return", f"${metrics['total_return']:,.2f}"),
            ("Total Return %", f"{metrics['total_return_pct']:.2f}%"),
            ("Total Trades", str(metrics['total_trades'])),
            ("Win Rate", f"{metrics['win_rate']:.2f}%"),
            ("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}"),
            ("Max Drawdown", f"{metrics['max_drawdown_pct']:.2f}%"),
            ("Profit Factor", f"{metrics['profit_factor']:.2f}"),
            ("Average Trade", f"${metrics.get('avg_win', 0) + metrics.get('avg_loss', 0):,.2f}"),
        ]

        self.results_table.setRowCount(len(data))
        for i, (label, value) in enumerate(data):
            self.results_table.setItem(i, 0, QTableWidgetItem(label))
            item = QTableWidgetItem(value)
            if "%" in value or "-" in value or isinstance(metrics.get(label.lower()), float):
                if float(value.replace("%", "").replace("$", "").replace(",", "")) < 0:
                    item.setForeground(QColor("red"))
                else:
                    item.setForeground(QColor("green"))
            self.results_table.setItem(i, 1, item)

    def display_trades(self, trades: List[dict]):
        """Display executed trades"""
        self.trades_table.setRowCount(len(trades))
        for i, trade in enumerate(trades):
            self.trades_table.setItem(i, 0, QTableWidgetItem(trade['entry_date'][:10]))
            self.trades_table.setItem(i, 1, QTableWidgetItem(trade['exit_date'][:10]))
            self.trades_table.setItem(i, 2, QTableWidgetItem(f"${trade['entry_price']:.2f}"))
            self.trades_table.setItem(i, 3, QTableWidgetItem(f"${trade['exit_price']:.2f}"))
            self.trades_table.setItem(i, 4, QTableWidgetItem(f"{trade['quantity']:.0f}"))
            
            pnl_item = QTableWidgetItem(f"${trade['pnl']:.2f}")
            pnl_color = QColor("green") if trade['pnl'] > 0 else QColor("red")
            pnl_item.setForeground(pnl_color)
            self.trades_table.setItem(i, 5, pnl_item)

            pnl_pct_item = QTableWidgetItem(f"{trade['pnl_pct']:.2f}%")
            pnl_pct_item.setForeground(pnl_color)
            self.trades_table.setItem(i, 6, pnl_pct_item)

    def display_equity_chart(self, equity_curve: List[float]):
        """Display equity curve chart"""
        chart = QChart()
        chart.setTitle("Equity Curve")
        chart.setAnimationOptions(QChart.SeriesAnimations)

        series = QLineSeries()
        series.setName("Equity")
        for i, value in enumerate(equity_curve):
            series.append(QPointF(i, value))

        chart.addSeries(series)
        chart.createDefaultAxes()
        
        self.chart_view.setChart(chart)

    def compare_strategies(self):
        """Compare selected strategies"""
        strategies = []
        if self.compare_ema_check.isChecked():
            strategies.append("EMA Crossover")
        if self.compare_sma_check.isChecked():
            strategies.append("SMA Crossover")
        if self.compare_rsi_check.isChecked():
            strategies.append("RSI Strategy")
        if self.compare_macd_check.isChecked():
            strategies.append("MACD Strategy")
        if self.compare_bollinger_check.isChecked():
            strategies.append("Bollinger Bands")

        if not strategies:
            QMessageBox.warning(self, "Warning", "Please select at least one strategy")
            return

        QMessageBox.information(self, "Info", f"Comparing {len(strategies)} strategies...\n(Running backtests...)")
        self.statusBar.showMessage(f"Comparing {len(strategies)} strategies...")

    def save_results(self, results: dict):
        """Save backtest results to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"results/backtest_{results['symbol']}_{timestamp}.json"
        Path("results").mkdir(exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"Results saved to {filename}")

    def load_recent_results(self):
        """Load recent backtest results into archive"""
        results_dir = Path("results")
        if not results_dir.exists():
            return
        
        json_files = sorted(results_dir.glob("backtest_*.json"), reverse=True)[:10]
        for f in json_files:
            try:
                with open(f) as file:
                    data = json.load(file)
                    item_text = f"{data.get('symbol', 'N/A')} - {data.get('strategy', 'N/A')} - {data.get('start_date', 'N/A')}"
                    self.archive_list.addItem(item_text)
            except:
                pass

    def view_archive_details(self):
        """View details of archived result"""
        QMessageBox.information(self, "Details", "Click on a result to view details")

    def export_archive(self):
        """Export archived result to CSV"""
        QMessageBox.information(self, "Export", "Select a result and click Export")

    def delete_archive(self):
        """Delete archived result"""
        QMessageBox.information(self, "Delete", "Select a result to delete")


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    dashboard = QuantumTradeDashboard()
    dashboard.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
