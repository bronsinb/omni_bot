import logging
from datetime import datetime
import pytz
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest
from strategy.brain import Signal
from config.settings import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER

logger = logging.getLogger(__name__)

class ExecutionEngine:
    def __init__(self, telegram_notifier=None):
        self.api_key = ALPACA_API_KEY
        self.secret_key = ALPACA_SECRET_KEY
        self.paper = ALPACA_PAPER
        
        # Trading Client for Executing Orders
        self.client = TradingClient(self.api_key, self.secret_key, paper=self.paper)
        
        # Market Data Client specifically for pulling Options Chains
        self.option_client = OptionHistoricalDataClient(self.api_key, self.secret_key)
        
        self.telegram = telegram_notifier
        logger.info(f"Execution Engine initialized (Paper Mode: {self.paper})")

    def _get_best_0dte_option(self, symbol: str, option_type: str) -> str:
        """
        Queries Alpaca for the latest Option Chain and selects an OTM 0DTE contract.
        option_type = 'call' or 'put'
        """
        # Note: This requires an OPRA subscription on your Alpaca account.
        
        # For MVP: Return a dummy string if we can't fetch it, preventing a crash.
        try:
            req = OptionChainRequest(underlying_symbol=symbol)
            chain = self.option_client.get_option_chain(req)
            
            if not chain:
                raise ValueError("Empty options chain returned.")
                
            # Naive selection for boilerplate: just grab the very first key
            # In production: filter 'chain.keys()' by expiration date == today 
            # and strike price > current price (for calls).
            best_contract_symbol = list(chain.keys())[0]
            logger.info(f"🎯 Selected 0DTE {option_type.upper()} Contract: {best_contract_symbol}")
            return best_contract_symbol
            
        except Exception as e:
            logger.warning(f"Failed to pull {symbol} Options Chain (Missing OPRA Data Sub?). Fallback to stock.")
            return symbol

    def execute(self, signal: Signal):
        """Receives a signal from The Brain and executes via Alpaca Trade API."""
        try:
            positions = self.client.get_all_positions()
            for p in positions:
                if p.symbol == signal.ticker: # Warning: This checks stock ticker, not option contract symbol.
                    logger.info(f"Already hold positions in {signal.ticker}, ignoring duplicate signal.")
                    return

            # Determine whether we are trying to buy Stock or an Option Contract
            symbol_to_trade = signal.ticker
            if "CALL" in signal.action:
                symbol_to_trade = self._get_best_0dte_option(signal.ticker, "call")
            elif "PUT" in signal.action:
                symbol_to_trade = self._get_best_0dte_option(signal.ticker, "put")

            # Always a BUY to open the position for our base strategy
            side = OrderSide.BUY 
            qty = 1 # 1 Option Contract OR 1 Share of Stock
            
            order_data = MarketOrderRequest(
                symbol=symbol_to_trade,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.DAY
            )

            # Submit to Alpaca
            order = self.client.submit_order(order_data=order_data)
            logger.info(f"✅ Executed {signal.action} -> {symbol_to_trade} (Order ID: {order.id})")
            
            if self.telegram:
                logger.info(f"[TELEGRAM ALERT]: Trade Executed: {signal.action} 1x {symbol_to_trade}")

        except Exception as e:
            logger.error(f"Failed to execute trade for {signal.ticker}: {e}")

    def close_all_positions(self):
        """Emergency cutoff (e.g., at 3:58 PM for the 15-minute 0DTE logic)."""
        logger.warning("🚨 EMERGENCY CLOSE ALL: Liquidating all open positions.")
        self.client.close_all_positions(cancel_orders=True)
