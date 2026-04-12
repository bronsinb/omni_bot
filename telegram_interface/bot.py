import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config.settings import TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

class TelegramBotNotifier:
    def __init__(self, token: str):
        self.token = token
        self.chat_id = TELEGRAM_CHAT_ID
        self.app = Application.builder().token(token).build()
        self._setup_handlers()
        
        # Bot State flags that elements like main.py can check
        self.is_paused = False

    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("pause", self.cmd_pause))
        self.app.add_handler(CommandHandler("resume", self.cmd_resume))
        self.app.add_handler(CommandHandler("report", self.cmd_report))
        self.app.add_handler(CommandHandler("help", self.cmd_help))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🤖 Omnichannel Trading Bot Online! Send /status to see current state.")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        status = "⏸ PAUSED" if self.is_paused else "▶️ RUNNING (TRADING ACTIVE)"
        await update.message.reply_text(f"Bot Status: {status}\nMonitoring SPY 15-min strategy & Alternative Data.")

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.is_paused = True
        await update.message.reply_text("⏸ Bot has paused execution. Analyzing but NOT taking new trades.")
        
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.is_paused = False
        await update.message.reply_text("▶️ Bot execution resumed. actively trading.")

    async def cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # We will connect this to the Analytics Engine later
        report = "📊 DAILY REPORT:\nPnL: $0.00\nActive Positions: None\nML Confidence: Accumulating Data"
        await update.message.reply_text(report)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "🛠 **Available Commands**\n\n"
            "/start - Initialize communication with the bot\n"
            "/status - Check current bot status (Running / Paused)\n"
            "/pause - Pause trading execution (keeps monitoring)\n"
            "/resume - Resume trading execution\n"
            "/report - Get a daily summary report\n"
            "/help - Show this help message"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def send_message(self, text: str):
        """Used by the main trading loop to send unsolicited alerts."""
        if not self.chat_id:
            logger.warning("No TELEGRAM_CHAT_ID set! Cannot send message.")
            return
            
        try:
            await self.app.bot.send_message(chat_id=self.chat_id, text=text)
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def start(self):
        """Initializes and runs the bot in the background event loop."""
        logger.info("Initializing Telegram Bot...")
        await self.app.initialize()
        await self.app.start()
        # Uses long polling to listen for /commands
        await self.app.updater.start_polling()
        await self.send_message("🟢 Bot system initialized and waiting for commands.")
