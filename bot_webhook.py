import logging
import os
import random
import string
import asyncio # تم إضافة هذا للاستخدام مع asyncio.sleep

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
import warnings # لاستخدام warnings.filterwarnings

# تجاهل التحذير المحدد من مكتبة python-telegram-bot (إذا استمر الظهور)
# هذا السطر يجب أن يكون بعد الاستيرادات وقبل إعداد logging
warnings.filterwarnings(
    "ignore",
    message="If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message.",
    category=UserWarning,
    module="telegram.ext.conversationhandler"
)

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Telegram token
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN environment variable not set! Please set it on Railway.")

# States
INITIAL_MENU, ASK_EXAMPLE, BULK_LIST = range(3)

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔤 Generate Username", callback_data='generate')],
        [InlineKeyboardButton("📄 Bulk Check List", callback_data='bulk')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to RipperTek Bot. Please choose:", reply_markup=reply_markup)
    return INITIAL_MENU

# Callback query handler (for buttons)
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
        # إعادة عرض القائمة الأولية
        keyboard = [
            [InlineKeyboardButton("🔤 Generate Username", callback_data='generate')],
            [InlineKeyboardButton("📄 Bulk Check List", callback_data='bulk')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Welcome to RipperTek Bot. Please choose:", reply_markup=reply_markup)
        return INITIAL_MENU # العودة إلى حالة القائمة الأولية

    return ConversationHandler.END

# Username generator logic
def generate_usernames(pattern, limit=20):
    letters = string.ascii_lowercase + string.digits # Include digits for more variety
    generated = set()
    attempts = 0 # لحماية من حلقات لا نهائية إذا كان النمط صعب التوليد
    max_attempts_per_username = 100

    while len(generated) < limit and attempts < limit * max_attempts_per_username:
        uname = list(pattern) # تحويل النمط إلى قائمة من الأحرف لتسهيل الاستبدال
        
        # استبدال 'a', 'b', 'c' في النمط
        # هذا الجزء يفترض أن النمط سيحتوي على 'a', 'b', 'c' كأماكن للاستبدال
        # مثال: "user_a_b_c"
        # إذا كان النمط "xxxx", ستحتاج إلى تحديد رموز placeholder أخرى
        for i in range(len(uname)):
            if uname[i] == 'a':
                uname[i] = random.choice(letters)
            elif uname[i] == 'b':
                uname[i] = random.choice(letters)
            elif uname[i] == 'c':
                uname[i] = random.choice(letters)
        
        final_uname = "".join(uname)

        # إضافة قيود على طول اسم المستخدم قبل التحقق
        if 5 <= len(final_uname) <= 32 and final_uname.replace('_', '').isalnum():
            generated.add(final_uname)
        attempts += 1

    return list(generated)


# Telegram API username availability checker
async def check_username_availability(context: ContextTypes.DEFAULT_TYPE, username: str) -> bool:
    # Telegram username rules: 5-32 chars, a-z, 0-9, underscores. Must not start with underscore.
    if not (5 <= len(username) <= 32 and username[0] != '_' and username.replace('_', '').isalnum()):
        logger.warning(f"Invalid username format or length (client-side check): {username}")
        return False

    try:
        # Attempt to get chat info. If it exists, it's not available for new public channels/groups.
        chat = await context.bot.get_chat(f"@{username}")
        # If get_chat succeeds and the chat has that exact username, it's taken.
        if chat.username and chat.username.lower() == username.lower():
            logger.info(f"Username @{username} already exists (get_chat successful). Chat ID: {chat.id}")
            return False
        # In some edge cases, get_chat might succeed for private chats without a public username.
        # But generally, if get_chat doesn't raise BadRequest, it's not available.
        return False
    except BadRequest as e:
        error_message = str(e).lower()
        # "username not found" or "chat not found" are indicators that the username is available.
        if "username not found" in error_message or "chat not found" in error_message:
            logger.info(f"Username @{username} is likely available (BadRequest: {error_message}).")
            return True
        logger.error(f"Telegram API BadRequest checking username {username}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking username {username}: {e}")

    return False

# Handle generated pattern
async def ask_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = update.message.text.strip()
    # يمكنك وضع بعض التحقق من صحة النمط هنا
    if not pattern:
        await update.message.reply_text("Please provide a valid pattern.")
        return ASK_EXAMPLE #Stay in the same state

    raw_usernames = generate_usernames(pattern, limit=200) # زيادة المحاولات للعثور على 20 متاحين

    available = []
    await update.message.reply_text("Searching for available usernames, please wait...")
    
    for uname in raw_usernames:
        if await check_username_availability(context, uname):
            available.append(uname)
            if len(available) >= 20: # عرض أول 20 اسم متاح
                break
        await asyncio.sleep(0.05) # تأخير بسيط لتجنب FloodWait

    if available:
        text = "✅ First 20 available usernames:\n" + "\n".join(available)
    else:
        text = "😔 No available usernames found for your pattern."

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# Handle bulk checking
async def bulk_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [n.strip() for n in update.message.text.splitlines() if n.strip()]
    if not names:
        await update.message.reply_text("Please provide a list of usernames.")
        return BULK_LIST #Stay in the same state

    available = []
    await update.message.reply_text("Checking your list, please wait...")

    for name in names:
        if await check_username_availability(context, name):
            available.append(name)
        await asyncio.sleep(0.05) # تأخير بسيط لتجنب FloodWait

    if available:
        text = "✅ Available usernames:\n" + "\n".join(available)
    else:
        text = "😔 None of the provided usernames are available."

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# Cancel command handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled. Type /start to begin again.")
    return ConversationHandler.END

# Main application setup and run
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    # Define the ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)], # Conversation starts with /start command
        states={
            # After /start, we are in INITIAL_MENU, waiting for a button press
            INITIAL_MENU: [CallbackQueryHandler(button)],
            ASK_EXAMPLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_example)],
            BULK_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_list)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            # This CallbackQueryHandler for 'back' makes the button work from any state.
            CallbackQueryHandler(button, pattern="^back$")
        ],
        # Important: Set per_message=False for ConversationHandler itself to handle callbacks from any message
        per_message=False
    )

    # Add the ConversationHandler to the application
    app.add_handler(conv_handler)

    # Webhook or Polling configuration
    PORT = int(os.getenv("PORT", "8080")) # Default to 8080 for Railway
    WEBHOOK_URL = os.getenv("WEBHOOK_URL") # This should be set in Railway (e.g., https://your-app.railway.app)
    
    # This is the crucial part for debugging WEBHOOK_SECRET_PATH
    WEBHOOK_SECRET_PATH = os.getenv("WEBHOOK_SECRET_PATH", f"webhook_{os.urandom(16).hex()}")
    logger.info(f"DEBUG: WEBHOOK_SECRET_PATH being used: {WEBHOOK_SECRET_PATH}") # <<< DEBUG LINE

    if WEBHOOK_URL:
        logger.info(f"Starting Webhook at {WEBHOOK_URL}/{WEBHOOK_SECRET_PATH} on port {PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_SECRET_PATH, # The unique path for Telegram to send updates
            webhook_url=f"{WEBHOOK_URL}/{WEBHOOK_SECRET_PATH}" # Full URL for Telegram to call
        )
    else:
        logger.warning("No WEBHOOK_URL set. Running in polling mode. This is not recommended for production on Railway.")
        app.run_polling() # Fallback to polling for local testing if WEBHOOK_URL is not set
