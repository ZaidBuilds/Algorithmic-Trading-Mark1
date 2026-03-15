"""Unified decision engine combining technical, ML, and AI signals."""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, List
from datetime import datetime
from ml.feature_engineer import FeatureEngineer
from ml.ml_predictor import MLPredictor
from ai.ollama_advisor import OllamaAdvisor
import warnings

warnings.filterwarnings('ignore')


class UnifiedDecisionEngine:
    """
    Combines technical indicators, ML predictions, and AI insights 
    into unified trading decisions.
    
    Three-layer decision making:
    1. Technical Layer: Traditional indicators (RSI, MACD, etc)
    2. ML Layer: Machine learning price prediction
    3. AI Layer: Ollama reasoning and context understanding
    """
    
    def __init__(self, use_ai: bool = True):
        """
        Initialize decision engine.
        
        Args:
            use_ai: Whether to include Ollama AI (requires running Ollama)
        """
        self.feature_engineer = FeatureEngineer()
        self.ml_predictor = None  # Will be trained when model is provided
        self.ai_advisor = OllamaAdvisor() if use_ai else None
        self.decision_history = []
        self.use_ai = use_ai
    
    def process_price_data(self, df: pd.DataFrame) -> Dict:
        """
        Process OHLCV data through all three layers.
        
        Args:
            df: DataFrame with columns [Open, High, Low, Close, Volume]
            
        Returns:
            Dictionary with signals from each layer
        """
        # Layer 1: Technical Analysis
        df_features = self.feature_engineer.engineer_features(df.copy())
        technical_signals = self._extract_technical_signals(df_features)
        
        # Layer 2: ML Prediction
        ml_signals = None
        if self.ml_predictor and self.ml_predictor.trained:
            X, _ = self.feature_engineer.get_feature_matrix(df_features)
            if len(X) > 0:
                X_norm = self.feature_engineer.normalize_features(X, fit=False)
                ml_signals = self._extract_ml_signals(X_norm[-1:])
        
        # Layer 3: AI Analysis
        ai_context = None
        if self.use_ai and self.ai_advisor and self.ai_advisor.connected:
            ai_context = self._extract_ai_signals(
                technical_signals, 
                ml_signals,
                df.iloc[-1]
            )
        
        return {
            'timestamp': datetime.now(),
            'technical': technical_signals,
            'ml': ml_signals,
            'ai': ai_context,
            'price': df.iloc[-1]['Close']
        }
    
    def _extract_technical_signals(self, df: pd.DataFrame) -> Dict[str, float]:
        """Extract technical indicator signals."""
        last_row = df.iloc[-1]
        
        signals = {}
        
        # RSI Signal (0-1 scale)
        if pd.notna(last_row['rsi']):
            rsi = last_row['rsi']
            if rsi > 70:
                signals['rsi'] = 0.2  # Overbought - bearish
            elif rsi < 30:
                signals['rsi'] = 0.8  # Oversold - bullish
            else:
                signals['rsi'] = 0.5  # Neutral
        
        # MACD Signal
        if pd.notna(last_row['macd']) and pd.notna(last_row['macd_signal']):
            if last_row['macd'] > last_row['macd_signal']:
                signals['macd'] = 0.7  # Bullish crossover
            else:
                signals['macd'] = 0.3  # Bearish
        
        # SMA Trend
        if pd.notna(last_row['sma_20']) and pd.notna(last_row['sma_50']):
            if last_row['sma_20'] > last_row['sma_50']:
                signals['sma_trend'] = 0.7  # Bullish
            else:
                signals['sma_trend'] = 0.3  # Bearish
        
        # Bollinger Bands Position
        if pd.notna(last_row['bb_position']):
            signals['bb_position'] = last_row['bb_position']  # 0-1 scale
        
        # Price vs EMA
        if pd.notna(last_row['ema_12']):
            ema_signal = 0.7 if last_row['Close'] > last_row['ema_12'] else 0.3
            signals['price_ema'] = ema_signal
        
        return signals
    
    def _extract_ml_signals(self, X: np.ndarray) -> Dict:
        """Extract ML model signals."""
        if not self.ml_predictor or not self.ml_predictor.trained:
            return None
        
        predictions, probabilities = self.ml_predictor.predict(X)
        
        return {
            'prediction': int(predictions[0]),  # 0=down, 1=up
            'confidence': float(probabilities[0]),
            'model_type': self.ml_predictor.model_type,
            'certainty': 'high' if probabilities[0] > 0.8 else 'medium' if probabilities[0] > 0.6 else 'low'
        }
    
    def _extract_ai_signals(self, technical: Dict, ml: Optional[Dict], 
                           current_price_row: pd.Series) -> Dict:
        """Extract AI advisor signals."""
        if not self.ai_advisor:
            return None
        
        # Ask AI for analysis
        analysis = self.ai_advisor.analyze_signals(
            technical,
            current_price_row['Close'],
            'SYMBOL'
        )
        
        return {
            'analysis': analysis,
            'advisor_model': self.ai_advisor.model,
            'confidence': 'high' if self.ai_advisor.connected else 'offline'
        }
    
    def generate_decision(self, signal_data: Dict) -> Dict:
        """
        Generate unified trading decision from all signals.
        
        Args:
            signal_data: Output from process_price_data()
            
        Returns:
            Dictionary with decision, confidence, rationale
        """
        technical = signal_data.get('technical', {})
        ml = signal_data.get('ml')
        ai = signal_data.get('ai')
        
        # Calculate signal strength (0-1)
        if technical:
            bullish_signals = sum(1 for v in technical.values() if v > 0.5)
            signal_strength = bullish_signals / len(technical)
        else:
            signal_strength = 0.5
        
        # ML confidence
        ml_strength = ml['confidence'] if ml else 0.5
        
        # Weighted decision
        weights = {
            'technical': 0.35,
            'ml': 0.40,
            'ai': 0.25
        }
        
        technical_score = signal_strength * weights['technical']
        ml_score = (ml['prediction'] if ml else 0.5) * weights['ml']
        
        final_score = technical_score + ml_score
        
        # Adjust for AI if available
        if ai and self.ai_advisor.connected:
            if 'bearish' in ai['analysis'].lower() or 'down' in ai['analysis'].lower():
                final_score *= 0.9
            elif 'bullish' in ai['analysis'].lower() or 'up' in ai['analysis'].lower():
                final_score *= 1.1
        
        final_score = min(1.0, max(0.0, final_score))
        
        # Generate decision
        decision = 'BUY' if final_score > 0.55 else 'SELL' if final_score < 0.45 else 'HOLD'
        
        rationale = self._build_rationale(
            decision, signal_strength, ml, technical, ai, final_score
        )
        
        decision_dict = {
            'decision': decision,
            'confidence': final_score,
            'timestamp': signal_data['timestamp'],
            'price': signal_data['price'],
            'rationale': rationale,
            'component_scores': {
                'technical': signal_strength,
                'ml': ml_strength if ml else None,
                'final': final_score
            },
            'signals': {
                'technical': technical,
                'ml': ml,
                'ai': ai
            }
        }
        
        self.decision_history.append(decision_dict)
        return decision_dict
    
    def _build_rationale(self, decision: str, tech_strength: float, 
                        ml: Optional[Dict], technical: Dict,
                        ai: Optional[Dict], score: float) -> str:
        """Build human-readable decision rationale."""
        parts = []
        
        # Technical rationale
        if tech_strength > 0.6:
            parts.append(f"Technical indicators show bullish setup ({tech_strength:.0%})")
        elif tech_strength < 0.4:
            parts.append(f"Technical indicators are bearish ({tech_strength:.0%})")
        else:
            parts.append("Technical indicators are mixed")
        
        # ML rationale
        if ml:
            direction = "predicts UP" if ml['prediction'] == 1 else "predicts DOWN"
            parts.append(f"ML model {direction} ({ml['confidence']:.0%} confidence)")
        
        # AI rationale  
        if ai and ai.get('analysis'):
            parts.append(f"AI analysis: {ai['analysis'][:100]}...")
        
        return ". ".join(parts)
    
    def train_ml_model(self, df: pd.DataFrame, model_type: str = 'random_forest'):
        """
        Train ML component on historical data.
        
        Args:
            df: Historical OHLCV data
            model_type: 'random_forest' or 'gradient_boosting'
        """
        print(f"Training ML model ({model_type})...")
        
        # Engineer features
        df_features = self.feature_engineer.engineer_features(df)
        X, y = self.feature_engineer.get_feature_matrix(df_features)
        
        if len(X) < 50:
            print(f"⚠ Only {len(X)} samples - need at least 50 to train")
            return False
        
        # Normalize
        X_norm = self.feature_engineer.normalize_features(X, fit=True)
        
        # Train model
        self.ml_predictor = MLPredictor(model_type=model_type)
        metrics = self.ml_predictor.train(X_norm, y)
        
        print(f"✓ ML Model trained")
        print(f"  Accuracy: {metrics['accuracy']:.2%}")
        print(f"  Precision: {metrics['precision']:.2%}")
        print(f"  Recall: {metrics['recall']:.2%}")
        
        return True
    
    def get_decision_history(self) -> List[Dict]:
        """Get all decisions made."""
        return self.decision_history
    
    def performance_summary(self) -> Dict:
        """Get summary of decision performance."""
        if not self.decision_history:
            return {'total_decisions': 0}
        
        history = pd.DataFrame(self.decision_history)
        
        return {
            'total_decisions': len(history),
            'buy_signals': len(history[history['decision'] == 'BUY']),
            'sell_signals': len(history[history['decision'] == 'SELL']),
            'hold_signals': len(history[history['decision'] == 'HOLD']),
            'avg_confidence': history['confidence'].mean(),
            'latest_decision': history.iloc[-1]['decision'] if len(history) > 0 else None
        }


# Example usage and testing
if __name__ == "__main__":
    print("=" * 70)
    print("UNIFIED DECISION ENGINE TESTING")
    print("=" * 70)
    
    # Create sample data
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    
    df = pd.DataFrame({
        'Open': 100 + np.cumsum(np.random.randn(100) * 0.5),
        'High': 102 + np.cumsum(np.random.randn(100) * 0.5),
        'Low': 98 + np.cumsum(np.random.randn(100) * 0.5),
        'Close': 100 + np.cumsum(np.random.randn(100) * 0.5),
        'Volume': np.random.randint(1000000, 5000000, 100)
    }, index=dates)
    
    # Initialize engine
    print("\n1. INITIALIZING ENGINE")
    print("-" * 70)
    engine = UnifiedDecisionEngine(use_ai=False)  # Set to True if Ollama running
    print("✓ Engine initialized")
    print(f"  AI enabled: {engine.use_ai}")
    
    # Train ML model on historical data
    print("\n2. TRAINING ML MODEL")
    print("-" * 70)
    engine.train_ml_model(df.iloc[:80], model_type='random_forest')
    
    # Process latest price data
    print("\n3. PROCESSING LATEST PRICE DATA")
    print("-" * 70)
    signal_data = engine.process_price_data(df.iloc[:90])
    print(f"✓ Signals processed")
    print(f"  Current price: ${signal_data['price']:.2f}")
    print(f"  Technical signals: {len(signal_data['technical'])} indicators")
    print(f"  ML prediction available: {signal_data['ml'] is not None}")
    
    # Generate decision
    print("\n4. GENERATING UNIFIED DECISION")
    print("-" * 70)
    decision = engine.generate_decision(signal_data)
    
    print(f"✓ Decision: {decision['decision']}")
    print(f"  Confidence: {decision['confidence']:.1%}")
    print(f"  Technical strength: {decision['component_scores']['technical']:.1%}")
    if decision['component_scores']['ml']:
        print(f"  ML confidence: {decision['component_scores']['ml']:.1%}")
    
    print(f"\n  Rationale: {decision['rationale']}")
    
    # Performance summary
    print("\n5. PERFORMANCE SUMMARY")
    print("-" * 70)
    summary = engine.performance_summary()
    print(f"✓ Total decisions: {summary['total_decisions']}")
    print(f"  Buy signals: {summary['buy_signals']}")
    print(f"  Sell signals: {summary['sell_signals']}")
    print(f"  Avg confidence: {summary['avg_confidence']:.1%}")
    
    print("\n" + "=" * 70)
    print("✓ ALL COMPONENTS WORKING")
    print("=" * 70)
