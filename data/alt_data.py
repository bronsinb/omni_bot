import asyncio
import logging
import time
from finvizfinance.quote import finvizfinance

logger = logging.getLogger(__name__)

class AltDataEngine:
    def __init__(self):
        # The Semaphore ensures we only make ONE web request at a time across the entire bot
        # This completely eliminates Claude's "DDoS / IP Ban" race condition
        self.semaphore = asyncio.Semaphore(1)
        
        # TTL Caches so we don't spam requests for data that doesn't change fast
        # Format: { "AAPL": {"timestamp": 1234567, "data": {...} } }
        self.sentiment_cache = {}
        self.insider_cache = {}
        
        self.CACHE_TTL_SECONDS = 900 # 15 minutes
        
        # SEC User Agent
        self.sec_headers = {'User-Agent': 'OmnichannelBot bot@example.com'}

    async def get_finviz_sentiment(self, ticker: str) -> dict:
        """Fetches sentiment/analyst ratings from Finviz with strict rate limiting."""
        now = time.time()
        
        # 1. Check Cache First
        if ticker in self.sentiment_cache:
            if now - self.sentiment_cache[ticker]['timestamp'] < self.CACHE_TTL_SECONDS:
                return self.sentiment_cache[ticker]['data']

        # 2. Acquire Semaphore (Wait in line)
        async with self.semaphore:
            logger.info(f"Rate Limiter [Finviz]: Scraping sentiment for {ticker}...")
            try:
                # finvizfinance makes blocking HTTP requests under the hood, so technically 
                # we should run it in a threadpool to not block asyncio operations, 
                # but for this MVP, this is sufficient.
                # To make it truly async-safe we use asyncio.to_thread
                stock = await asyncio.to_thread(finvizfinance, ticker)
                
                # We can extract useful ML features like "Target Price", "RSI", etc.
                # However, scraping unstructured sentiment is complex, so we will grab basic fundamental scores
                fund_data = await asyncio.to_thread(stock.ticker_fundament)
                
                # Mock sentiment construction based on Analyst Recommedations
                # Recom typically goes from 1.0 (Strong Buy) to 5.0 (Strong Sell)
                recom_str = fund_data.get('Recom', '3.0')
                try:
                    recom_score = float(recom_str)
                except ValueError:
                    recom_score = 3.0
                    
                sentiment = {
                    "analyst_recom": recom_score,
                    "target_price": fund_data.get('Target Price', '0'),
                    "raw_news": [] # Implement news parsing later if needed
                }
                
                # Save to cache
                self.sentiment_cache[ticker] = {
                    "timestamp": now,
                    "data": sentiment
                }
                
                # Sleep a tiny bit to be polite to the Finviz server even inside the semaphore
                await asyncio.sleep(1)
                
                return sentiment
                
            except Exception as e:
                logger.error(f"Failed to fetch Finviz data for {ticker}: {e}")
                return {"analyst_recom": 3.0, "target_price": "0"}

    async def get_sec_insider_trades(self, ticker: str) -> list:
        """Fetches Form 4 Insider Trades from SEC Edgar..."""
        now = time.time()
        
        if ticker in self.insider_cache:
            if now - self.insider_cache[ticker]['timestamp'] < self.CACHE_TTL_SECONDS:
                return self.insider_cache[ticker]['data']

        async with self.semaphore:
            logger.info(f"Rate Limiter [SEC]: Scraping insider trades for {ticker}...")
            # For MVP, we will mock this as parsing SEC Edgar natively requires heavy XML/BS4 logic
            # that is out of scope for the immediate boilerplate.
            await asyncio.sleep(1) 
            
            mock_data = [] # In production, this returns [{"insider": "Tim Cook", "action": "SELL", "amount": 50000}]
            
            self.insider_cache[ticker] = {
                "timestamp": now,
                "data": mock_data
            }
            return mock_data

    async def update_all_alt_data(self, tickers: list) -> dict:
        """Called by the main loop to seamlessly grab all Alternative Data."""
        alt_state_dict = {}
        for ticker in tickers:
            sentiment = await self.get_finviz_sentiment(ticker)
            insiders = await self.get_sec_insider_trades(ticker)
            
            alt_state_dict[ticker] = {
                "finviz_sentiment": sentiment,
                "sec_insiders": insiders
            }
        return alt_state_dict
