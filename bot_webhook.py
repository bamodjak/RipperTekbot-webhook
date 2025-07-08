import logging
import os
import random
import string

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Telegram token
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN environment variable not set!")

# States
INITIAL_MENU, ASK_EXAMPLE, BULK_LIST = range(3)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔤 Generate Username", callback_data='generate')],
        [InlineKeyboardButton("📄 Bulk Check List", callback_data='bulk')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to RipperTek Bot. Please choose:", reply_markup=reply_markup)
    return INITIAL_MENU

# Callback query handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'generate':
        await query.edit_message_text("Send a sample pattern (e.g., a_b_c):")
        return ASK_EXAMPLE
    elif query.data == 'bulk':
        await query.edit_message_text("Send a list of usernames (one per line):")
        return BULK_LIST
    elif query.data == 'back':
        await query.edit_message_text("Welcome to RipperTek Bot. Please choose:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔤 Generate Username", callback_data='generate')],
            [InlineKeyboardButton("📄 Bulk Check List", callback_data='bulk')]
        ]))
        return INITIAL_MENU

    return ConversationHandler.END

# Username generator logic
def generate_usernames(pattern, limit=20):
    letters = string.ascii_lowercase + string.digits
    generated = set()

    while len(generated) < limit:
        uname = pattern
        for char_to_replace in ['a', 'b', 'c']:
             if char_to_replace in uname:
                uname = uname.replace(char_to_replace, random.choice(letters), 1)

        if uname not in generated:
            generated.add(uname)

    return list(generated)

# Telegram API username availability checker
async def check_username_availability(context, username):
    if not (5 <= len(username) <= 32 and username.replace('_', '').isalnum()):
        logger.warning(f"Invalid username format or length: {username}")
        return False

    try:
        chat = await context.bot.get_chat(f"@{username}")
        if chat.username and chat.username.lower() == username.lower():
            logger.info(f"Username @{username} already exists (get_chat successful).")
            return False
        return False
    except BadRequest as e:
        error_message = str(e).lower()
        if "username not found" in error_message or "chat not found" in error_message:
            logger.info(f"Username @{username} is likely available (BadRequest: {error_message}).")
            return True
        logger.error(f"Error checking username {username}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking username {username}: {e}")

    return False

# Handle generated pattern
async def ask_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = update.message.text.strip()
    raw_usernames = generate_usernames(pattern, limit=100)

    available = []
    for uname in raw_usernames:
        # await asyncio.sleep(0.1) # أضف هذا إذا كنت تريد تأخير (تذكر استيراد asyncio)
        if await check_username_availability(context, uname):
            available.append(uname)
            if len(available) >= 20:
                break

    if available:
        text = "✅ First 20 available usernames:\n" + "\n".join(available)
    else:
        text = "😔 No available usernames found."

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# Handle bulk checking
async def bulk_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [n.strip() for n in update.message.text.splitlines() if n.strip()]
    available = []

    for name in names:
        # await asyncio.sleep(0.1) # أضف هذا إذا كنت تريد تأخير (تذكر استيراد asyncio)
        if await check_username_availability(context, name):
            available.append(name)

    if available:
        text = "✅ Available usernames:\n" + "\n".join(available)
    else:
        text = "😔 None are available."

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# Cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# Webhook or Polling start
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            # هنا يتم إزالة per_message=False من CallbackQueryHandler
            INITIAL_MENU: [CallbackQueryHandler(button)],
            ASK_EXAMPLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_example)],
            BULK_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_list)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            # وهنا أيضاً يتم إزالة per_message=False
            CallbackQueryHandler(button, pattern="^back$")
        ],
        # ولكن يتم إضافة per_message=False هنا في ConversationHandler
        per_message=False
    )

    app.add_handler(conv_handler)

    # Webhook config
    PORT = int(os.getenv("PORT", "8080"))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    WEBHOOK_SECRET_PATH = os.getenv("WEBHOOK_SECRET_PATH", f"webhook_{os.urandom(16).hex()}")

    if WEBHOOK_URL:
        logger.info(f"Starting Webhook at {WEBHOOK_URL}/{WEBHOOK_SECRET_PATH}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_SECRET_PATH,
            webhook_url=f"{WEBHOOK_URL}/{WEBHOOK_SECRET_PATH}"
        )
    else:
        logger.warning("No WEBHOOK_URL set. Running in polling mode.")
        app.run_polling()
