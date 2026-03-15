"""Machine learning model for price direction prediction."""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from typing import Tuple, Dict, Optional
import pickle
import os
import warnings

warnings.filterwarnings('ignore')


class MLPredictor:
    """
    Machine learning model for predicting stock price direction.
    
    Supported Models:
    - Random Forest (default): Fast, robust, good for feature importance
    - Gradient Boosting: Slower but often more accurate
    - Logistic Regression: Simple baseline
    """
    
    def __init__(self, model_type: str = 'random_forest', random_state: int = 42):
        """
        Initialize ML predictor.
        
        Args:
            model_type: 'random_forest', 'gradient_boosting', or 'logistic_regression'
            random_state: For reproducibility
        """
        self.model_type = model_type
        self.random_state = random_state
        self.model = None
        self.feature_importance = None
        self.trained = False
        self.metrics = None
        
        self._init_model()
    
    def _init_model(self):
        """Initialize the selected model."""
        if self.model_type == 'random_forest':
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=15,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=self.random_state,
                n_jobs=-1
            )
        elif self.model_type == 'gradient_boosting':
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5,
                random_state=self.random_state
            )
        elif self.model_type == 'logistic_regression':
            self.model = LogisticRegression(
                max_iter=1000,
                random_state=self.random_state
            )
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")
    
    def train(self, X: np.ndarray, y: np.ndarray, 
              test_size: float = 0.2) -> Dict[str, float]:
        """
        Train the model.
        
        Args:
            X: Training features (shape: n_samples, n_features)
            y: Training targets (shape: n_samples,)
            test_size: Fraction of data to use for testing
            
        Returns:
            Dictionary with accuracy, precision, recall, f1
        """
        if len(X) < 50:
            raise ValueError("Need at least 50 samples to train")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=self.random_state
        )
        
        # Train model
        self.model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test)
        
        self.metrics = {
            'accuracy': accuracy_score(y_test, y_pred),
            'precision': precision_score(y_test, y_pred, zero_division=0),
            'recall': recall_score(y_test, y_pred, zero_division=0),
            'f1': f1_score(y_test, y_pred, zero_division=0),
            'test_size': len(X_test),
            'train_size': len(X_train)
        }
        
        # Get feature importance if available
        if hasattr(self.model, 'feature_importances_'):
            self.feature_importance = self.model.feature_importances_
        
        self.trained = True
        return self.metrics
    
    def predict(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Make predictions.
        
        Args:
            X: Feature matrix (shape: n_samples, n_features)
            
        Returns:
            predictions: Class labels (0 or 1)
            probabilities: Probability of class 1
        """
        if not self.trained:
            raise ValueError("Model must be trained before prediction")
        
        predictions = self.model.predict(X)
        probabilities = self.model.predict_proba(X)[:, 1]
        
        return predictions, probabilities
    
    def predict_single(self, features: np.ndarray) -> Tuple[int, float]:
        """
        Predict for a single sample.
        
        Args:
            features: Single sample features (shape: n_features,)
            
        Returns:
            prediction: 0 (down) or 1 (up)
            probability: Confidence (0.5-1.0)
        """
        features = features.reshape(1, -1)
        pred, prob = self.predict(features)
        return int(pred[0]), float(prob[0])
    
    def save(self, filepath: str):
        """Save model to disk."""
        if not self.trained:
            raise ValueError("Can only save trained models")
        
        with open(filepath, 'wb') as f:
            pickle.dump(self, f)
    
    def load(self, filepath: str):
        """Load model from disk."""
        with open(filepath, 'rb') as f:
            saved = pickle.load(f)
        
        self.model = saved.model
        self.trained = saved.trained
        self.metrics = saved.metrics
        self.feature_importance = saved.feature_importance
    
    def get_feature_importance(self, feature_names: Optional[list] = None) -> Dict[str, float]:
        """
        Get feature importance ranking.
        
        Args:
            feature_names: Optional list of feature names
            
        Returns:
            Dictionary mapping feature names to importance scores
        """
        if self.feature_importance is None:
            return {}
        
        if feature_names is None:
            feature_names = [f'feature_{i}' for i in range(len(self.feature_importance))]
        
        importance_dict = dict(zip(feature_names, self.feature_importance))
        return dict(sorted(importance_dict.items(), key=lambda x: x[1], reverse=True))
    
    def get_metrics(self) -> Dict[str, float]:
        """Get training metrics."""
        return self.metrics if self.metrics else {}


# Example usage and testing
if __name__ == "__main__":
    # Create sample training data
    np.random.seed(42)
    n_samples = 200
    n_features = 20
    
    X = np.random.randn(n_samples, n_features)
    y = (X[:, 0] + X[:, 1] + np.random.randn(n_samples) * 0.5 > 0).astype(int)
    
    print("=" * 50)
    print("ML PREDICTOR TESTING")
    print("=" * 50)
    
    # Test Random Forest
    print("\n1. RANDOM FOREST MODEL")
    print("-" * 50)
    rf = MLPredictor(model_type='random_forest')
    metrics = rf.train(X, y)
    print(f"✓ Model trained ({rf.model_type})")
    print(f"  Accuracy:  {metrics['accuracy']:.4f}")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  Recall:    {metrics['recall']:.4f}")
    print(f"  F1:        {metrics['f1']:.4f}")
    
    # Single prediction
    test_sample = X[0:1]
    pred, prob = rf.predict(test_sample)
    print(f"\n✓ Prediction for sample:")
    print(f"  Direction: {'UP' if pred[0] else 'DOWN'}")
    print(f"  Confidence: {prob[0]:.2%}")
    
    # Feature importance
    feature_names = [f'feature_{i}' for i in range(n_features)]
    importance = rf.get_feature_importance(feature_names)
    print(f"\n✓ Top 5 important features:")
    for i, (feat, imp) in enumerate(list(importance.items())[:5], 1):
        print(f"  {i}. {feat}: {imp:.4f}")
    
    # Test Gradient Boosting
    print("\n2. GRADIENT BOOSTING MODEL")
    print("-" * 50)
    gb = MLPredictor(model_type='gradient_boosting')
    metrics = gb.train(X, y)
    print(f"✓ Model trained ({gb.model_type})")
    print(f"  Accuracy:  {metrics['accuracy']:.4f}")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  Recall:    {metrics['recall']:.4f}")
    print(f"  F1:        {metrics['f1']:.4f}")
    
    # Test saving/loading
    print("\n3. SAVE/LOAD TEST")
    print("-" * 50)
    model_path = "test_model.pkl"
    rf.save(model_path)
    print(f"✓ Model saved to {model_path}")
    
    rf2 = MLPredictor()
    rf2.load(model_path)
    print(f"✓ Model loaded successfully")
    
    # Verify predictions match
    pred1, prob1 = rf.predict(test_sample)
    pred2, prob2 = rf2.predict(test_sample)
    match = np.allclose(prob1, prob2)
    print(f"  Predictions match: {match}")
    
    if os.path.exists(model_path):
        os.remove(model_path)
        print(f"✓ Test file cleaned up")
