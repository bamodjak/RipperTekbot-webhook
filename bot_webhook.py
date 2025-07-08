import logging
import os
import random
import string
import asyncio
import warnings

# Suppress the PTBUserWarning
warnings.filterwarnings(
    "ignore",
    message="If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message.",
    category=UserWarning,
    module="telegram.ext.conversationhandler"
)

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
    raise RuntimeError("TELEGRAM_TOKEN environment variable not set! Please set it on Railway.")

# States for ConversationHandler (تم تعديل الحالات لإضافة ASK_COUNT وتغيير ASK_EXAMPLE إلى ASK_PATTERN)
INITIAL_MENU, ASK_COUNT, ASK_PATTERN, BULK_LIST, HOW_TO_INFO = range(5)

# --- Helper Function to create Main Menu Keyboard ---
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔤 Generate Username", callback_data='generate')],
        [InlineKeyboardButton("📄 Bulk Check List", callback_data='bulk')],
        [InlineKeyboardButton("❓ How To", callback_data='how_to')]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Stop & Back Buttons Keyboard Helper ---
def get_stop_and_back_keyboard():
    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data='back')],
        [InlineKeyboardButton("🛑 Stop", callback_data='stop')]
    ]
    return InlineKeyboardMarkup(keyboard)


# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to RipperTek Bot. Please choose:", reply_markup=get_main_menu_keyboard())
    return INITIAL_MENU

# Callback query handler (for all inline buttons)
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'generate':
        # عند الضغط على 'Generate'، نطلب العدد أولاً
        await query.edit_message_text("How many names would you like to generate and check (1-100)?", reply_markup=get_stop_and_back_keyboard())
        return ASK_COUNT # الانتقال إلى الحالة الجديدة ASK_COUNT
    elif query.data == 'bulk':
        await query.edit_message_text("Send a list of usernames (one per line):", reply_markup=get_stop_and_back_keyboard())
        return BULK_LIST
    elif query.data == 'how_to':
        await query.edit_message_text(
            "**How RipperTek Bot Works:**\n\n"
            "This bot helps you find available Telegram usernames. "
            "You can either:\n\n"
            "1. **Generate Usernames:** First, tell me how many names to find, then provide a pattern like `user_a_b_c` (where 'a', 'b', 'c' are placeholders that will be replaced by random letters/digits). The bot will generate variations and check their availability.\n\n" # تم تحديث الشرح
            "2. **Bulk Check List:** Send a list of usernames (one per line) and the bot will check each one for availability.\n\n"
            "**Aim:** To simplify the process of finding unique and unused Telegram usernames for your channels, groups, or personal profiles.\n\n"
            "**Note:** Username availability checks are based on Telegram's API behavior (attempting to get chat info). While generally accurate, there might be edge cases (e.g., private channels) that affect results.",
            parse_mode='Markdown',
            reply_markup=get_stop_and_back_keyboard()
        )
        return HOW_TO_INFO
    elif query.data == 'back' or query.data == 'stop':
        await query.edit_message_text(
            "Welcome to RipperTek Bot. Please choose:",
            reply_markup=get_main_menu_keyboard()
        )
        return INITIAL_MENU

    return ConversationHandler.END

# New handler to ask for the number of names to generate
async def handle_count_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text.strip())
        if not (1 <= count <= 100): # تحديد نطاق للعدد
            await update.message.reply_text("Please enter a number between 1 and 100.", reply_markup=get_stop_and_back_keyboard())
            return ASK_COUNT # البقاء في نفس الحالة إذا كان العدد خارج النطاق
        
        context.user_data['num_to_generate_display'] = count # حفظ العدد في user_data
        await update.message.reply_text("Send a sample pattern (e.g., `user_a_b_c` where 'a', 'b', 'c' are replaced by random chars/digits):", parse_mode='Markdown', reply_markup=get_stop_and_back_keyboard())
        return ASK_PATTERN # الانتقال إلى طلب النمط
    except ValueError:
        await update.message.reply_text("That's not a valid number. Please enter a number.", reply_markup=get_stop_and_back_keyboard())
        return ASK_COUNT # البقاء في نفس الحالة إذا لم يكن إدخالاً رقمياً


# Username generator logic (بدون تغيير في عملها، فقط اسم المعامل)
def generate_usernames(pattern: str, num_variations_to_try: int = 200) -> list[str]:
    letters = string.ascii_lowercase + string.digits
    generated = set()
    attempts = 0
    max_attempts = num_variations_to_try * 5 # زيادة محاولات التوليد

    while len(generated) < num_variations_to_try and attempts < max_attempts:
        uname_chars = list(pattern)
        
        for i in range(len(uname_chars)):
            if uname_chars[i] in ['a', 'b', 'c']:
                uname_chars[i] = random.choice(letters)
        
        final_uname = "".join(uname_chars)

        if 5 <= len(final_uname) <= 32 and final_uname[0] != '_' and final_uname.replace('_', '').isalnum():
            generated.add(final_uname)
        attempts += 1
    
    return [name for name in list(generated) if 5 <= len(name) <= 32 and name[0] != '_' and name.replace('_', '').isalnum()]


# Telegram API username availability checker
async def check_username_availability(context: ContextTypes.DEFAULT_TYPE, username: str) -> bool:
    if not (5 <= len(username) <= 32 and username[0] != '_' and username.replace('_', '').isalnum()):
        logger.warning(f"Invalid username format or length (pre-API check): {username}")
        return False

    try:
        chat = await context.bot.get_chat(f"@{username}")
        
        if chat.username and chat.username.lower() == username.lower():
            logger.info(f"Username @{username} already exists (get_chat successful). Chat ID: {chat.id}")
            return False
        
        return False
    except BadRequest as e:
        error_message = str(e).lower()
        if "username not found" in error_message or "chat not found" in error_message:
            logger.info(f"Username @{username} is likely available (BadRequest: {error_message}).")
            return True
        logger.error(f"Telegram API BadRequest checking username {username}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking username {username}: {e}")

    return False

# Handle generated pattern request (تم تغيير الاسم إلى ask_pattern ليتناسب مع التدفق الجديد)
async def ask_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = update.message.text.strip().lower()
    if not pattern:
        await update.message.reply_text("Please provide a valid pattern.", reply_markup=get_stop_and_back_keyboard())
        return ASK_PATTERN

    num_to_display = context.user_data.get('num_to_generate_display', 20) # استرجاع العدد من user_data
    num_variations_to_try = num_to_display * 10 # محاولة توليد عدد أكبر لضمان العثور على المطلوب

    await update.message.reply_text(f"Searching for {num_to_display} available usernames, please wait...", reply_markup=get_stop_and_back_keyboard())
    
    raw_usernames = generate_usernames(pattern, num_variations_to_try) # تمرير العدد الكلي للمحاولات
    logger.info(f"DEBUG_GENERATE: Pattern: '{pattern}', Generated {len(raw_usernames)} raw names. First 10: {raw_usernames[:10]}")
    
    available = []
    
    for uname in raw_usernames:
        if await check_username_availability(context, uname):
            available.append(uname)
            if len(available) >= num_to_display: # استخدام العدد المطلوب للعرض
                break
        await asyncio.sleep(0.05)

    if available:
        text = f"✅ First {len(available)} available usernames:\n" + "\n".join(available)
    else:
        text = f"😔 No available usernames found for your pattern '{pattern}' after checking {len(raw_usernames)} variations. Try a different pattern (remember 'a','b','c' are placeholders)."

    await update.message.reply_text(text, reply_markup=get_stop_and_back_keyboard())
    return INITIAL_MENU # العودة إلى القائمة الرئيسية بعد الانتهاء

# Handle bulk checking request
async def bulk_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [n.strip() for n in update.message.text.splitlines() if n.strip()]
    if not names:
        await update.message.reply_text("Please provide a list of usernames.", reply_markup=get_stop_and_back_keyboard())
        return BULK_LIST

    await update.message.reply_text("Checking your list, please wait...", reply_markup=get_stop_and_back_keyboard())

    available = []
    for name in names:
        if await check_username_availability(context, name):
            available.append(name)
        await asyncio.sleep(0.05)

    if available:
        text = "✅ Available usernames:\n" + "\n".join(available)
    else:
        text = "😔 None of the provided usernames are available."

    await update.message.reply_text(text, reply_markup=get_stop_and_back_keyboard())
    return INITIAL_MENU # العودة إلى القائمة الرئيسية بعد الانتهاء

# Cancel command handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled. Type /start to begin again.", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END

# Main application setup and run
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            INITIAL_MENU: [CallbackQueryHandler(button)],
            
            # حالة جديدة لطلب العدد
            ASK_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_count_input),
                CallbackQueryHandler(button, pattern="^back$|^stop$") # Back/Stop buttons work here
            ],

            # حالة طلب النمط (تم تغيير الاسم)
            ASK_PATTERN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_pattern),
                CallbackQueryHandler(button, pattern="^back$|^stop$") # Back/Stop buttons work here
            ],
            
            BULK_LIST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_list),
                CallbackQueryHandler(button, pattern="^back$|^stop$") # Back/Stop buttons work here
            ],
            HOW_TO_INFO: [
                CallbackQueryHandler(button, pattern="^back$|^stop$") # Back/Stop buttons work here
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(button, pattern="^back$|^stop$") # Global Back/Stop fallback
        ],
        per_message=False
    )

    app.add_handler(conv_handler)

    PORT = int(os.getenv("PORT", "8080"))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    
    WEBHOOK_SECRET_PATH = os.getenv("WEBHOOK_SECRET_PATH", f"webhook_{os.urandom(16).hex()}")
    logger.info(f"DEBUG: WEBHOOK_SECRET_PATH being used: {WEBHOOK_SECRET_PATH}")

    if WEBHOOK_URL:
        logger.info(f"Starting Webhook at {WEBHOOK_URL}/{WEBHOOK_SECRET_PATH} on port {PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_SECRET_PATH,
            webhook_url=f"{WEBHOOK_URL}/{WEBHOOK_SECRET_PATH}"
        )
    else:
        logger.warning("No WEBHOOK_URL set. Running in polling mode. This is not recommended for production on Railway.")
        app.run_polling()
