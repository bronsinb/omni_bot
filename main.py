import asyncio
import logging
from config.settings import TELEGRAM_BOT_TOKEN

from data.ingestion import DataEngine
from data.alt_data import AltDataEngine
from strategy.brain import AnalyticsEngine
from execution.broker import ExecutionEngine
from telegram_interface.bot import TelegramBotNotifier

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_trading_loop():
    logger.info("Starting Omnichannel Trading Bot...")
    
    # Initialization phase
    data_engine = DataEngine()
    alt_data_engine = AltDataEngine()
    analytics_engine = AnalyticsEngine()
    telegram_bot = TelegramBotNotifier(token=TELEGRAM_BOT_TOKEN)
    
    # Pass telegram bot in for alerts
    execution_engine = ExecutionEngine(telegram_notifier=telegram_bot)
    
    # Prime the Brain with historical data immediately
    data_engine.fetch_historical_bars(symbols=["SPY", "QQQ", "AAPL", "TSLA"], days_back=5)

    # Start independent async tasks
    asyncio.create_task(telegram_bot.start())
    asyncio.create_task(data_engine.start_stream())

    # Main Trading Loop
    try:
        while True:
            # Wait 60 seconds before each strategy check
            await asyncio.sleep(60)
            
            # 1. Fetch latest state from the webhooks & scrape Alt Data (with strict Semaphores/Caching!)
            current_market_state = data_engine.get_latest_state()
            alt_market_state = await alt_data_engine.update_all_alt_data(["SPY", "QQQ", "AAPL", "TSLA"])
            
            # Merge alternative data into the current market state for the Brain
            # E.g. {"prices": {}, "historical": {}, "alt_data": {'AAPL': {'finviz_sentiment':...}}}
            current_market_state['alt_data'] = alt_market_state

            # 2. Check Signals (Include last 15 min SPY MOC logic inside analytics engine)
            signals = analytics_engine.evaluate(current_market_state)

            # 3. Execute Trades! (Only if bot is NOT paused via Telegram)
            if not telegram_bot.is_paused:
                for sig in signals: 
                    if sig.action != 'HOLD':
                        # Execute the trade
                        execution_engine.execute(sig)
                        # Immediately alert via Telegram await
                        await telegram_bot.send_message(f"⚡️ SIGNAL FIRED & EXECUTED ⚡️\n\nTicker: {sig.ticker}\nAction: {sig.action}\nConfidence: {sig.confidence * 100}%\nReason: {sig.reason}")
            else:
                logger.warning("Bot is currently PAUSED via Telegram. Signals ignored.")

            # 4. Learning Phase (evaluate past trades)
            # analytics_engine.evaluate_past_trades_and_learn([])

            logger.info(f"Strategist Check Complete. SPY Price: {current_market_state['prices'].get('SPY', 0.0)}")

    except KeyboardInterrupt:
        logger.info("Shutting down bot gracefully.")
    except Exception as e:
        logger.error(f"Critical Error in main loop: {e}")
        await telegram_bot.send_message(f"🚨 CRITICAL BOT ERROR 🚨\n{e}")

if __name__ == "__main__":
    asyncio.run(run_trading_loop())
