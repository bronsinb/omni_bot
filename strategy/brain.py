import os
import json
import logging
import pandas as pd
import pandas_ta as ta
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

class Signal:
    def __init__(self, ticker: str, action: str, confidence: float, reason: str, generated_by_indicators: list = None):
        self.ticker = ticker
        self.action = action  # 'BUY_CALL', 'BUY_PUT', 'BUY_STOCK', 'SELL', 'HOLD'
        self.confidence = confidence
        self.reason = reason
        # Track which specific logic branches triggered this so we can penalize/reward them
        self.generated_by_indicators = generated_by_indicators or ["TA"]

class AnalyticsEngine:
    def __init__(self):
        self.market_regime = "NORMAL" # Could be BULL, BEAR, CHOPPY
        self.learning_state_file = "config/learning_state.json"
        
        # Default Weights (Claude's structural idea!)
        self.learned_weights = {
            "BULL": {"TA": 0.3, "MOC_IMBALANCE": 0.5, "SENTIMENT": 0.2},
            "BEAR": {"TA": 0.4, "MOC_IMBALANCE": 0.4, "SENTIMENT": 0.2},
            "CHOPPY": {"TA": 0.1, "MOC_IMBALANCE": 0.8, "SENTIMENT": 0.1},
            "NORMAL": {"TA": 0.33, "MOC_IMBALANCE": 0.33, "SENTIMENT": 0.33}
        }
        
        self.load_learning_state()

    def load_learning_state(self):
        """Loads historical weights from disk, allowing the AI to survive restarts."""
        if os.path.exists(self.learning_state_file):
            try:
                with open(self.learning_state_file, 'r') as f:
                    self.learned_weights = json.load(f)
                logger.info("🧠 Brain loaded previous learning state from disk.")
            except Exception as e:
                logger.error(f"Failed to load learning state: {e}")
        else:
            self.save_learning_state() # Create the file

    def save_learning_state(self):
        """Saves current weights to disk."""
        try:
            with open(self.learning_state_file, 'w') as f:
                json.dump(self.learned_weights, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save learning state: {e}")

    def determine_regime(self, spy_historical: pd.DataFrame):
        """A simple logic to determine market condition based on SPY."""
        if spy_historical is None or spy_historical.empty:
            return "NORMAL"
            
        # Refined Logic: SPY compared to its 9 EMA
        # If it's consistently above by a solid margin, it's BULL.
        spy_historical.ta.ema(length=9, append=True)
        if 'EMA_9' in spy_historical.columns:
            latest_price = spy_historical['close'].iloc[-1]
            latest_ema = spy_historical['EMA_9'].iloc[-1]
            if latest_price > latest_ema * 1.002:
                return "BULL"
            elif latest_price < latest_ema * 0.998:
                return "BEAR"
            else:
                return "CHOPPY"
                
        return "NORMAL"

    def evaluate_15_min_close_strategy(self, state: dict, ticker: str) -> Signal:
        """The core 0DTE logic that runs from 3:45 PM to 3:58 PM EST."""
        est_tz = pytz.timezone('US/Eastern')
        now_est = datetime.now(est_tz)
        
        is_last_15 = (now_est.hour == 15 and now_est.minute >= 45)
        
        current_price = state['prices'].get(ticker, 0.0)
        historical_df = state['historical'].get(ticker)
        alt_data = state.get('alt_data', {}).get(ticker, {})
        
        if historical_df is None or historical_df.empty:
            return Signal(ticker, 'HOLD', 0.0, "Waiting for data.", ["TA"])

        historical_df.ta.ema(length=9, append=True)
        historical_df.ta.rsi(length=14, append=True)
        
        latest_rsi = historical_df['RSI_14'].iloc[-1] if 'RSI_14' in historical_df.columns else 50
        
        # Example dynamic confidence calculation using our learned weights
        base_confidence = 0.50
        regime_weights = self.learned_weights.get(self.market_regime, self.learned_weights["NORMAL"])
        ta_weight = regime_weights.get("TA", 0.33)
        
        # If deeply oversold in the last 15 min, huge reversal probability
        if is_last_15 and latest_rsi < 30:
            adjusted_confidence = base_confidence + (ta_weight * 0.5) 
            return Signal(ticker, 'BUY_CALL', adjusted_confidence, f"15-Min 0DTE Reversal. RSI: {latest_rsi:.2f}", ["TA", "MOC_IMBALANCE"])
        elif is_last_15 and latest_rsi > 70:
            adjusted_confidence = base_confidence + (ta_weight * 0.5)
            return Signal(ticker, 'BUY_PUT', adjusted_confidence, f"15-Min 0DTE Top out. RSI: {latest_rsi:.2f}", ["TA", "MOC_IMBALANCE"])
            
        # Basic placeholder to trigger trades natively for Option 1 testing if not 3:45 PM
        # If Finviz Sentiment analyst targets are screaming "Buy" and RSI is low (but not end of day)
        finviz_sentiment = alt_data.get('finviz_sentiment', {})
        analyst_recom = finviz_sentiment.get('analyst_recom', 3.0) # 1.0 is Strong Buy, 5.0 is Strong Sell
        
        if analyst_recom < 2.0 and latest_rsi < 40:
            return Signal(ticker, 'BUY_STOCK', 0.70, f"Strong Analyst Buy + Low RSI", ["TA", "SENTIMENT"])
            
        return Signal(ticker, 'HOLD', 0.0, "No strong signal.", ["TA"])

    def evaluate(self, current_market_state: dict) -> list[Signal]:
        """Runs every minute when new data ticks in."""
        signals = []
        spy_hist = current_market_state['historical'].get('SPY')
        self.market_regime = self.determine_regime(spy_hist)
        
        for ticker in current_market_state['prices'].keys():
            signal = self.evaluate_15_min_close_strategy(current_market_state, ticker)
            if signal.action != 'HOLD':
                logger.info(f"🚨 SIGNAL DETECTED [{ticker}]: {signal.action} (Confidence: {signal.confidence}) - Regime: {self.market_regime}")
                signals.append(signal)

        return signals

    def evaluate_past_trades_and_learn(self, trade_results: list):
        """
        Takes a list of dictionaries representing closed trades:
        [{"ticker": "SPY", "profit_pct": -0.05, "regime": "CHOPPY", "indicators_used": ["TA", "SENTIMENT"]}]
        """
        if not trade_results:
            return
            
        logger.info(f"🧠 Brain analyzing {len(trade_results)} past trades to adjust ML State...")
        
        for trade in trade_results:
            profit = trade.get("profit_pct", 0.0)
            regime = trade.get("regime", "NORMAL")
            indicators = trade.get("indicators_used", [])
            
            # Simple Reinforcement algorithm:
            # If trade won (>0.5%), bump up the weights of the indicators used slightly (0.01)
            # If trade lost (< -0.5%), explicitly decay the weights.
            adjustment = 0.0
            if profit > 0.005:
                adjustment = 0.02
            elif profit < -0.005:
                adjustment = -0.02
                
            if adjustment != 0.0:
                for ind in indicators:
                    current_weight = self.learned_weights[regime].get(ind, 0.33)
                    new_weight = max(0.01, min(0.99, current_weight + adjustment))
                    self.learned_weights[regime][ind] = round(new_weight, 3)
                    
                logger.info(f"🧠 Feedback Loop: Adjusted {regime} weights by {adjustment} due to trade profit {profit*100}%")
                
        # Commit new experiences to disk
        self.save_learning_state()


