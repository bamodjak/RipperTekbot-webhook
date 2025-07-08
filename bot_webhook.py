import logging
import os
import random
import string

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# ✅ Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ Token
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    logger.error("TELEGRAM_TOKEN not set!")
    # للتجريب المحلي فقط (أزل التعليق بحذر)
    # TOKEN = "YOUR_REAL_TOKEN"

# ✅ States
ASK_EXAMPLE, BULK_LIST = range(2)

# ✅ Start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔤 Generate Username", callback_data='generate')],
        [InlineKeyboardButton("📄 Bulk Check List", callback_data='bulk')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to RipperTek Bot. Please choose:", reply_markup=reply_markup)

# ✅ Button handling
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'generate':
        await query.edit_message_text("Send a sample pattern (like a_b_c):")
        return ASK_EXAMPLE
    elif query.data == 'bulk':
        await query.edit_message_text("Send a list of usernames (one per line):")
        return BULK_LIST
    return ConversationHandler.END

# ✅ Generate example
async def ask_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = update.message.text.strip()
    generated = generate_usernames(pattern)
    await update.message.reply_text("Generated usernames (first 20 available):\n" + "\n".join(generated[:20]))
    return ConversationHandler.END

# ✅ Bulk check
async def bulk_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [name.strip() for name in update.message.text.strip().splitlines() if name.strip()]
    available = [name for name in names if check_username(name)]
    if available:
        await update.message.reply_text("✅ Available:\n" + "\n".join(available))
    else:
        await update.message.reply_text("😔 No usernames available from your list.")
    return ConversationHandler.END

# ✅ Username generator
def generate_usernames(pattern):
    letters = string.ascii_lowercase
    result = []
    for char1 in letters:
        for char2 in letters:
            for char3 in letters:
                uname = pattern.replace('a', char1, 1).replace('b', char2, 1).replace('c', char3, 1)
                if check_username(uname):
                    result.append(uname)
                    if len(result) >= 100:
                        return result
    return result

# ✅ Username availability simulation (replace with actual check)
def check_username(username):
    logger.info(f"Checking username: {username} (Simulated)")
    return random.choice([True, False])

# ✅ Cancel handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# ✅ Main
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button)],
        states={
            ASK_EXAMPLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_example)],
            BULK_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_list)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    # ✅ Webhook settings
    PORT = int(os.environ.get("PORT", 8080))
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
    WEBHOOK_SECRET_PATH = "webhook_eb4f7a39c76a441a9b30f08d30f3c902"  # ثابت وآمن

    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL not set. Running in polling mode.")
        app.run_polling(poll_interval=3)
    else:
        logger.info(f"Starting webhook at {WEBHOOK_URL}/{WEBHOOK_SECRET_PATH} on port {PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_SECRET_PATH,
            webhook_url=f"{WEBHOOK_URL}/{WEBHOOK_SECRET_PATH}"
        )
