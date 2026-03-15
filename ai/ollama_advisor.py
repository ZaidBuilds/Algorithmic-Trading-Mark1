"""Ollama AI advisor for trading decisions."""

import requests
import json
from typing import Dict, Optional, List, Tuple
import warnings

warnings.filterwarnings('ignore')


class OllamaAdvisor:
    """
    Integration with Ollama for AI-powered trading advice.
    
    Uses local LLM to:
    - Analyze market conditions
    - Review trading signals
    - Suggest position sizing
    - Identify risk factors
    - Provide market context
    """
    
    def __init__(self, model: str = 'qwen2.5-coder:1.5b', host: str = 'http://localhost:11434'):
        """
        Initialize Ollama advisor.
        
        Args:
            model: Ollama model name (default: qwen2.5-coder:1.5b)
            host: Ollama server address
        """
        self.model = model
        self.host = host
        self.api_endpoint = f"{host}/api/generate"
        self.connected = False
        
        # Check connection
        self._check_connection()
    
    def _check_connection(self) -> bool:
        """Check if Ollama is running."""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=2)
            self.connected = response.status_code == 200
            return self.connected
        except Exception as e:
            print(f"⚠ Ollama not available: {e}")
            self.connected = False
            return False
    
    def analyze_signals(self, signals: Dict[str, float], 
                       current_price: float,
                       symbol: str = 'SYMBOL') -> str:
        """
        Ask Ollama to analyze trading signals.
        
        Args:
            signals: Dictionary of signal values (e.g., {'RSI': 65, 'MACD': 0.5})
            current_price: Current stock price
            symbol: Stock symbol
            
        Returns:
            AI analysis as string
        """
        if not self.connected:
            return self._offline_fallback("signal analysis", signals)
        
        prompt = f"""
        Analyze these trading signals for {symbol} at price ${current_price:.2f}:
        
        {chr(10).join([f"- {k}: {v:.2f}" for k, v in signals.items()])}
        
        Provide a brief assessment (2-3 sentences) of:
        1. Signal strength
        2. Confidence level
        3. Recommended action
        """
        
        return self._query_ollama(prompt)
    
    def assess_risk(self, position_size: float, 
                   entry_price: float,
                   stop_loss: float,
                   account_size: float) -> str:
        """
        Ask Ollama to assess position risk.
        
        Args:
            position_size: Number of shares
            entry_price: Entry price
            stop_loss: Stop loss level
            account_size: Total account size
            
        Returns:
            Risk assessment as string
        """
        if not self.connected:
            return self._offline_fallback("risk assessment", {
                'position_size': position_size,
                'risk_percent': abs((stop_loss - entry_price) / entry_price * 100)
            })
        
        risk_amount = abs(entry_price - stop_loss) * position_size
        risk_percent = (risk_amount / account_size) * 100
        
        prompt = f"""
        Assess position risk:
        - Entry: ${entry_price:.2f}
        - Stop Loss: ${stop_loss:.2f}
        - Position Size: {position_size:.0f} shares
        - Risk Amount: ${risk_amount:.2f}
        - Risk %: {risk_percent:.2f}% of account
        - Account Size: ${account_size:.2f}
        
        Is this a proper risk-reward setup? (2-3 sentences)
        """
        
        return self._query_ollama(prompt)
    
    def market_context(self, symbol: str,
                      latest_news: Optional[str] = None,
                      trend: Optional[str] = None) -> str:
        """
        Ask Ollama for market context and outlook.
        
        Args:
            symbol: Stock symbol
            latest_news: Recent news headlines
            trend: Current trend (uptrend, downtrend, sideways)
            
        Returns:
            Market context as string
        """
        if not self.connected:
            return self._offline_fallback("market context", {'symbol': symbol})
        
        prompt = f"""
        Summarize market context for {symbol}:
        Trend: {trend or 'unknown'}
        {'Recent news: ' + latest_news if latest_news else 'No recent news'}
        
        Briefly explain (2-3 sentences):
        1. Market sentiment
        2. Key risks
        3. Trade setup quality
        """
        
        return self._query_ollama(prompt)
    
    def validate_strategy(self, strategy_name: str,
                         win_rate: float,
                         profit_factor: float,
                         max_drawdown: float) -> str:
        """
        Ask Ollama to evaluate strategy performance.
        
        Args:
            strategy_name: Name of the strategy
            win_rate: Percentage of winning trades
            profit_factor: Gross profit / Gross loss
            max_drawdown: Maximum drawdown percentage
            
        Returns:
            Strategy evaluation as string
        """
        if not self.connected:
            return self._offline_fallback("strategy validation", {
                'name': strategy_name,
                'win_rate': win_rate
            })
        
        prompt = f"""
        Evaluate this trading strategy:
        
        Name: {strategy_name}
        Win Rate: {win_rate:.1%}
        Profit Factor: {profit_factor:.2f}
        Max Drawdown: {max_drawdown:.1%}
        
        Is this strategy viable for live trading? Explain briefly (3 sentences).
        """
        
        return self._query_ollama(prompt)
    
    def decision_synthesis(self, 
                          signals_summary: Dict[str, float],
                          ml_prediction: Tuple[int, float],
                          risk_assessment: str,
                          market_context: str) -> Dict:
        """
        Synthesize all signals into a unified decision.
        
        Args:
            signals_summary: Technical signals (0-1 scale)
            ml_prediction: (prediction: 0/1, confidence: 0-1)
            risk_assessment: Risk level text
            market_context: Market conditions text
            
        Returns:
            Dictionary with decision, confidence, rationale
        """
        # Count bullish signals
        bullish_count = sum(1 for v in signals_summary.values() if v > 0.5)
        signal_strength = bullish_count / len(signals_summary) if signals_summary else 0.5
        
        ml_pred, ml_conf = ml_prediction
        
        # Weighted decision
        weights = {
            'signals': 0.3,
            'ml': 0.4,
            'market': 0.3
        }
        
        signal_score = signal_strength * weights['signals']
        ml_score = ml_pred * weights['ml']
        
        final_score = signal_score + ml_score
        
        if not self.connected:
            return {
                'decision': 'BUY' if final_score > 0.5 else 'SELL',
                'confidence': final_score,
                'rationale': f"Based on {bullish_count} bullish signals and ML confidence {ml_conf:.0%}",
                'ai_insight': "Ollama offline - using technical analysis only"
            }
        
        # Ask Ollama for final insight
        prompt = f"""
        Final trading decision synthesis:
        - Technical signals strength: {signal_strength:.0%}
        - ML model prediction: {'UP' if ml_pred else 'DOWN'} (confidence: {ml_conf:.0%})
        - Risk level: {risk_assessment}
        - Market: {market_context}
        
        Provide final recommendation (BUY/SELL/HOLD) with 1-2 sentences of reasoning.
        """
        
        final_insight = self._query_ollama(prompt)
        
        return {
            'decision': 'BUY' if final_score > 0.5 else 'SELL',
            'confidence': final_score,
            'rationale': final_insight,
            'component_scores': {
                'signals': signal_strength,
                'ml': ml_conf,
                'combined': final_score
            }
        }
    
    def _query_ollama(self, prompt: str) -> str:
        """
        Query Ollama with a prompt.
        
        Args:
            prompt: Question or prompt for Ollama
            
        Returns:
            Response text
        """
        if not self.connected:
            return self._offline_fallback("query", {'prompt': prompt})
        
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.7
            }
            
            response = requests.post(self.api_endpoint, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('response', '').strip()
            else:
                return f"Error: Ollama returned {response.status_code}"
        
        except requests.exceptions.Timeout:
            return "Ollama response timeout - please check server"
        except Exception as e:
            return f"Error querying Ollama: {str(e)}"
    
    def _offline_fallback(self, operation: str, context: dict) -> str:
        """
        Fallback response when Ollama is offline.
        
        Provides reasonable default analysis without AI.
        """
        fallbacks = {
            "signal analysis": f"Ollama offline. Based on signal values: {context}",
            "risk assessment": f"Standard risk check: {abs(context.get('risk_percent', 0)):.1f}% portfolio risk",
            "market context": f"Unable to access market context for {context.get('symbol')}",
            "strategy validation": f"Strategy {context.get('name')} metrics received, Ollama unavailable",
            "query": "Ollama service not available. Using technical indicators only."
        }
        
        return fallbacks.get(operation, "Ollama offline - using defaults")
    
    def start_ollama_info(self) -> str:
        """
        Provide info on how to run Ollama locally.
        
        Returns:
            Installation and startup instructions
        """
        return """
        ╔═════════════════════════════════════════════╗
        ║         HOW TO RUN OLLAMA LOCALLY            ║
        ╚═════════════════════════════════════════════╝
        
        1. INSTALL OLLAMA
           Download from: https://ollama.ai
           - Windows: ollama-windows-installer
           - Mac: ollama-mac-installer
           - Linux: wget https://ollama.ai/install.sh && bash install.sh
        
        2. START OLLAMA SERVER
           In terminal: ollama serve
           
        3. DOWNLOAD A MODEL (in another terminal)
           ollama pull qwen2.5-coder:1.5b  # Recommended (Code-optimized, fast)
           ollama pull mistral              # Alternative (General purpose)
           ollama pull llama2               # Alternative (Accurate but slower)
        
        4. VERIFY SERVER IS RUNNING
           curl http://localhost:11434/api/tags
           Should show list of models
        
        5. NOW YOU CAN USE OLLAMA IN TRADING BOT
           Advisor will automatically connect and use it!
        
        ═══════════════════════════════════════════════
        """


# Example usage and testing
if __name__ == "__main__":
    print("=" * 60)
    print("OLLAMA ADVISOR TESTING")
    print("=" * 60)
    
    advisor = OllamaAdvisor()
    
    print(f"\n✓ Ollama Connection: {'CONNECTED' if advisor.connected else 'OFFLINE'}")
    
    if not advisor.connected:
        print("\n" + advisor.start_ollama_info())
    
    print("\n1. SIGNAL ANALYSIS")
    print("-" * 60)
    signals = {'RSI': 72, 'MACD': 1.2, 'SMA_trend': 1.0}
    analysis = advisor.analyze_signals(signals, 145.50, 'AAPL')
    print(f"Signals: {signals}")
    print(f"Analysis: {analysis}")
    
    print("\n2. RISK ASSESSMENT")
    print("-" * 60)
    risk = advisor.assess_risk(
        position_size=100,
        entry_price=150,
        stop_loss=145,
        account_size=10000
    )
    print(f"Risk Analysis: {risk}")
    
    print("\n3. MARKET CONTEXT")
    print("-" * 60)
    context = advisor.market_context('AAPL', trend='Uptrend')
    print(f"Market Context: {context}")
    
    print("\n4. STRATEGY VALIDATION")
    print("-" * 60)
    strategy_eval = advisor.validate_strategy(
        'EMA_Crossover',
        win_rate=0.58,
        profit_factor=1.8,
        max_drawdown=0.15
    )
    print(f"Strategy Eval: {strategy_eval}")
