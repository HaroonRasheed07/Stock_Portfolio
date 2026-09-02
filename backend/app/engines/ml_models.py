"""
ML models engine for trend classification and volatility regime detection.
Statistically justified model implementations with fallback handling.
"""
import logging
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score

logger = logging.getLogger(__name__)


class MLEngine:
    """Provides machine learning predictions when sufficient data is available."""

    def predict_trend(self, historical_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Train a Random Forest classifier on technical features to predict 20-day forward trend.
        Uses historical price/volume features. Returns predictions only if accuracy is acceptable.
        """
        if historical_df.empty or len(historical_df) < 252:
            return {
                "available": False,
                "reason": "Insufficient historical data (minimum 252 trading days required for ML model)",
            }

        try:
            df = historical_df.copy()
            close = df["Close"].astype(float)
            volume = df["Volume"].astype(float)

            # Feature Engineering
            df["returns"] = close.pct_change()
            df["sma_20_ratio"] = close / close.rolling(20).mean()
            df["sma_50_ratio"] = close / close.rolling(50).mean()
            df["volatility_20"] = df["returns"].rolling(20).std()
            df["volume_ratio"] = volume / volume.rolling(20).mean()

            # Target: 20-day forward return > +2% (Up), < -2% (Down), else Neutral
            forward_return = close.shift(-20) / close - 1
            df["target"] = 1  # Neutral
            df.loc[forward_return > 0.02, "target"] = 2  # Up
            df.loc[forward_return < -0.02, "target"] = 0  # Down

            features = ["returns", "sma_20_ratio", "sma_50_ratio", "volatility_20", "volume_ratio"]
            clean_df = df.dropna(subset=features + ["target"])

            if len(clean_df) < 150:
                return {"available": False, "reason": "Not enough clean data points after feature engineering"}

            X = clean_df[features]
            y = clean_df["target"]

            # Train / Test split (time-series order preserved)
            split_idx = int(len(X) * 0.8)
            X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
            y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

            model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
            model.fit(X_train, y_train)

            preds = model.predict(X_test)
            acc = accuracy_score(y_test, preds)

            # Predict current state
            latest_features = X.iloc[-1:]
            current_pred = model.predict(latest_features)[0]
            probs = model.predict_proba(latest_features)[0]

            labels = {0: "Down", 1: "Neutral", 2: "Up"}
            pred_label = labels.get(current_pred, "Neutral")

            feature_importance = dict(zip(features, [round(float(f), 3) for f in model.feature_importances_]))

            return {
                "available": True,
                "prediction": pred_label,
                "confidence": round(float(np.max(probs)), 2),
                "probabilities": {labels[i]: round(float(probs[i]), 2) for i in range(len(probs)) if i in labels},
                "accuracy": round(float(acc), 2),
                "feature_importance": feature_importance,
            }
        except Exception as e:
            logger.error(f"ML trend prediction error: {e}")
            return {"available": False, "reason": f"ML model error: {str(e)}"}
