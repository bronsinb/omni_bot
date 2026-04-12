import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.live import StockDataStream
from config.settings import ALPACA_API_KEY, ALPACA_SECRET_KEY, TICKERS_TO_WATCH

logger = logging.getLogger(__name__)

class DataEngine:
    def __init__(self):
        self.api_key = ALPACA_API_KEY
        self.secret_key = ALPACA_SECRET_KEY
        
        # Historical Client for getting past data (backtesting/TA calc)
        self.historical_client = StockHistoricalDataClient(self.api_key, self.secret_key)
        
        # Live Stream for real-time prices & MOC Imbalances
        # Note: If you don't have premium data, this connects to IEX automatically.
        self.stream = StockDataStream(self.api_key, self.secret_key)
        
        # Local state to hold the latest prices for the Strategy Engine
        self.latest_prices = {ticker: 0.0 for ticker in TICKERS_TO_WATCH}
        self.historical_data = {}

    def fetch_historical_bars(self, symbols: list, days_back: int = 5):
        """Fetches historical minute data to prime TA indicators."""
        logger.info(f"Fetching historical data for {symbols} over {days_back} days.")
        
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days_back)
        
        req = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Minute,
            start=start_time,
            end=end_time
        )
        
        bars = self.historical_client.get_stock_bars(req)
        
        # Convert to a dictionary of pandas DataFrames 
        df = bars.df
        for symbol in symbols:
            # Multi-index filtering for specific symbol
            if symbol in df.index.get_level_values('symbol'):
                symbol_df = df.xs(symbol, level='symbol')
                self.historical_data[symbol] = symbol_df
        
        logger.info("Historical data loaded.")
        return self.historical_data

    async def _handle_bar_update(self, bar):
        """Callback triggered every minute with new bar data from websocket."""
        logger.info(f"Live Price Update [{bar.symbol}]: {bar.close}")
        self.latest_prices[bar.symbol] = bar.close
        # Here we could emit an event to the Strategy Engine to recalculate immediately

    async def start_stream(self):
        """Connects to Alpaca websocket and listens for data indefinitely."""
        logger.info(f"Connecting to Alpaca Live Market Stream for {TICKERS_TO_WATCH}...")
        
        # Subscribe to minute bars
        self.stream.subscribe_bars(self._handle_bar_update, *TICKERS_TO_WATCH)
        
        # Run stream natively (blocks current thread so we should asyncio it in main loop)
        await self.stream._run_forever()

    def get_latest_state(self):
        """Returns the current state of tracked tickers for the brain/strategy evaluate."""
        return {
            "prices": self.latest_prices,
            "historical": self.historical_data
        }
