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

# States for ConversationHandler
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
        # تم تعديل رسالة الطلب لتوضح طريقة عمل النمط بـ 'x' كـ placeholder
        await query.edit_message_text("How many names would you like to generate and check (1-100)?", reply_markup=get_stop_and_back_keyboard())
        return ASK_COUNT
    elif query.data == 'bulk':
        await query.edit_message_text("Send a list of usernames (one per line):", reply_markup=get_stop_and_back_keyboard())
        return BULK_LIST
    elif query.data == 'how_to':
        await query.edit_message_text(
            "**How RipperTek Bot Works:**\n\n"
            "This bot helps you find available Telegram usernames. "
            "You can either:\n\n"
            "1. **Generate Usernames:** First, tell me how many names to find, then provide a pattern like `user_x_x_x` (where 'x' is a placeholder that will be replaced by random letters/digits). The bot will generate variations and check their availability.\n\n" # تم تحديث الشرح لـ 'x'
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
        if not (1 <= count <= 100):
            await update.message.reply_text("Please enter a number between 1 and 100.", reply_markup=get_stop_and_back_keyboard())
            return ASK_COUNT
        
        context.user_data['num_to_generate_display'] = count
        # تم تعديل رسالة الطلب لـ 'x' كـ placeholder
        await update.message.reply_text("Send a sample pattern (e.g., `user_x_x_x` where 'x' is replaced by random chars/digits):", parse_mode='Markdown', reply_markup=get_stop_and_back_keyboard())
        return ASK_PATTERN
    except ValueError:
        await update.message.reply_text("That's not a valid number. Please enter a number.", reply_markup=get_stop_and_back_keyboard())
        return ASK_COUNT


# Username generator logic (تم تعديل هذا الجزء لاستخدام 'x' كـ placeholder)
def generate_usernames(pattern: str, num_variations_to_try: int = 200) -> list[str]:
    letters = string.ascii_lowercase + string.digits
    generated = set()
    attempts = 0
    max_attempts = num_variations_to_try * 5
    
    PLACEHOLDER_CHAR = 'x' # <--- تم تعريف الـ placeholder هنا

    while len(generated) < num_variations_to_try and attempts < max_attempts:
        uname_chars = list(pattern)
        
        for i in range(len(uname_chars)):
            if uname_chars[i] == PLACEHOLDER_CHAR: # <--- تم التعديل للاستبدال فقط إذا كان الحرف هو 'x'
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

# Handle generated pattern request
async def ask_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = update.message.text.strip().lower()
    if not pattern:
        await update.message.reply_text("Please provide a valid pattern.", reply_markup=get_stop_and_back_keyboard())
        return ASK_PATTERN

    num_to_display = context.user_data.get('num_to_generate_display', 20)
    num_variations_to_try = num_to_display * 10 

    await update.message.reply_text(f"Searching for {num_to_display} available usernames based on '{pattern}', please wait...", reply_markup=get_stop_and_back_keyboard())
    
    raw_usernames = generate_usernames(pattern, num_variations_to_try)
    logger.info(f"DEBUG_GENERATE: Pattern: '{pattern}', Generated {len(raw_usernames)} raw names. First 10: {raw_usernames[:10]}")
    
    all_results = []
    
    for uname in raw_usernames:
        is_available = await check_username_availability(context, uname)
        all_results.append({'username': uname, 'available': is_available})
        await asyncio.sleep(0.05)

    available_names = [r['username'] for r in all_results if r['available']]
    taken_names = [r['username'] for r in all_results if not r['available']]

    # بناء رسالة النتيجة
    text_parts = [f"Checked {len(all_results)} variations for pattern '{pattern}'.\n"]

    if available_names:
        text_parts.append(f"✅ Available ({len(available_names)}):")
        text_parts.append("\n".join(available_names[:num_to_display]))
        if len(available_names) > num_to_display:
            text_parts.append(f"...and {len(available_names) - num_to_display} more available names.")
    else:
        text_parts.append("😔 No available usernames found among the generated ones.")

    # عرض الأسماء غير المتاحة (عدد محدود لتجنب رسائل طويلة جداً)
    if taken_names:
        MAX_TAKEN_TO_DISPLAY = 20
        text_parts.append(f"\n❌ Taken ({len(taken_names)}):")
        text_parts.append("\n".join(taken_names[:MAX_TAKEN_TO_DISPLAY]))
        if len(taken_names) > MAX_TAKEN_TO_DISPLAY:
            text_parts.append(f"...and {len(taken_names) - MAX_TAKEN_TO_DISPLAY} more taken names.")
    else:
        text_parts.append("\n🎉 All generated variations were found available! (Unlikely for large numbers)")


    final_text = "\n".join(text_parts)
    
    if len(final_text) > 4000:
        final_text = "Result too long to display fully. Showing summary:\n"
        final_text += f"Total checked: {len(all_results)}\n"
        final_text += f"✅ Available: {len(available_names)}\n"
        final_text += f"❌ Taken: {len(taken_names)}\n"
        final_text += "\nTry a smaller generation count for full list display, or use Bulk Check for specific lists."


    await update.message.reply_text(final_text, reply_markup=get_stop_and_back_keyboard())
    return INITIAL_MENU

# Handle bulk checking request
async def bulk_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [n.strip() for n in update.message.text.splitlines() if n.strip()]
    if not names:
        await update.message.reply_text("Please provide a list of usernames.", reply_markup=get_stop_and_back_keyboard())
        return BULK_LIST

    await update.message.reply_text("Checking your list, please wait...", reply_markup=get_stop_and_back_keyboard())

    all_results = []
    for name in names:
        is_available = await check_username_availability(context, name)
        all_results.append({'username': name, 'available': is_available})
        await asyncio.sleep(0.05)

    available_names = [r['username'] for r in all_results if r['available']]
    taken_names = [r['username'] for r in all_results if not r['available']]

    # بناء رسالة النتيجة
    text_parts = [f"Checked {len(all_results)} usernames from your list.\n"]

    if available_names:
        text_parts.append(f"✅ Available ({len(available_names)}):")
        text_parts.append("\n".join(available_names))
    else:
        text_parts.append("😔 None of the provided usernames are available.")

    if taken_names:
        MAX_TAKEN_TO_DISPLAY = 20
        text_parts.append(f"\n❌ Taken ({len(taken_names)}):")
        text_parts.append("\n".join(taken_names[:MAX_TAKEN_TO_DISPLAY]))
        if len(taken_names) > MAX_TAKEN_TO_DISPLAY:
            text_parts.append(f"...and {len(taken_names) - MAX_TAKEN_TO_DISPLAY} more taken names.")
        else:
            text_parts.append("\n".join(taken_names))
    else:
        text_parts.append("\n🎉 All provided usernames were found available! (Unlikely for large numbers)")

    final_text = "\n".join(text_parts)
    
    if len(final_text) > 4000:
        final_text = "Result too long to display fully. Showing summary:\n"
        final_text += f"Total checked: {len(all_results)}\n"
        final_text += f"✅ Available: {len(available_names)}\n"
        final_text += f"❌ Taken: {len(taken_names)}\n"
        final_text += "\nConsider smaller lists for full display."

    await update.message.reply_text(final_text, reply_markup=get_stop_and_back_keyboard())
    return INITIAL_MENU

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
            
            ASK_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_count_input),
                CallbackQueryHandler(button, pattern="^back$|^stop$")
            ],

            ASK_PATTERN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_pattern),
                CallbackQueryHandler(button, pattern="^back$|^stop$")
            ],
            
            BULK_LIST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_list),
                CallbackQueryHandler(button, pattern="^back$|^stop$")
            ],
            HOW_TO_INFO: [
                CallbackQueryHandler(button, pattern="^back$|^stop$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(button, pattern="^back$|^stop$")
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
