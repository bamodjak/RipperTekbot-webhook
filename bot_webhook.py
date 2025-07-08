import logging
import os
import random
import string
import asyncio # تم إضافة هذا للاستخدام مع asyncio.sleep
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

# States for ConversationHandler
INITIAL_MENU, ASK_EXAMPLE, BULK_LIST, HOW_TO_INFO = range(4) # Added HOW_TO_INFO state

# --- Helper Function to create Main Menu Keyboard ---
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔤 Generate Username", callback_data='generate')],
        [InlineKeyboardButton("📄 Bulk Check List", callback_data='bulk')],
        [InlineKeyboardButton("❓ How To", callback_data='how_to')] # Added How To button
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Stop & Back Buttons Keyboard Helper ---
def get_stop_and_back_keyboard():
    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data='back')],
        [InlineKeyboardButton("🛑 Stop", callback_data='stop')] # Added Stop button
    ]
    return InlineKeyboardMarkup(keyboard)


# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to RipperTek Bot. Please choose:", reply_markup=get_main_menu_keyboard())
    return INITIAL_MENU

# Callback query handler (for all inline buttons)
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Acknowledge the button press to the user

    if query.data == 'generate':
        await query.edit_message_text("Send a sample pattern (e.g., a_b_c):", reply_markup=get_stop_and_back_keyboard())
        return ASK_EXAMPLE
    elif query.data == 'bulk':
        await query.edit_message_text("Send a list of usernames (one per line):", reply_markup=get_stop_and_back_keyboard())
        return BULK_LIST
    elif query.data == 'how_to': # Handle 'How To' button
        await query.edit_message_text(
            "**How RipperTek Bot Works:**\n\n"
            "This bot helps you find available Telegram usernames. "
            "You can either:\n\n"
            "1. **Generate Usernames:** Provide a pattern like `a_b_c` (where 'a', 'b', 'c' are placeholders that will be replaced by random letters/digits). The bot will generate variations and check their availability.\n\n"
            "2. **Bulk Check List:** Send a list of usernames (one per line) and the bot will check each one for availability.\n\n"
            "**Aim:** To simplify the process of finding unique and unused Telegram usernames for your channels, groups, or personal profiles.\n\n"
            "**Note:** Username availability checks are based on Telegram's API behavior (attempting to get chat info). While generally accurate, there might be edge cases (e.g., private channels) that affect results.",
            parse_mode='Markdown', # Allows bold text
            reply_markup=get_stop_and_back_keyboard() # Offer stop/back from how-to screen
        )
        return HOW_TO_INFO # Stay in how-to state
    elif query.data == 'back' or query.data == 'stop': # Handle 'Back' and 'Stop' buttons
        # Edit the message to show the main menu again
        await query.edit_message_text(
            "Welcome to RipperTek Bot. Please choose:",
            reply_markup=get_main_menu_keyboard()
        )
        return INITIAL_MENU # Always go back to the main menu state

    return ConversationHandler.END # Fallback if unknown callback_data

# Username generator logic
def generate_usernames(pattern: str, limit: int = 20) -> list[str]:
    letters = string.ascii_lowercase + string.digits # Include letters and digits
    generated = set()
    attempts = 0
    max_attempts_per_username = 200 # Increased attempts for a better chance to find unique ones

    while len(generated) < limit and attempts < limit * max_attempts_per_username:
        uname_chars = list(pattern) # Convert pattern to a list of chars for mutable replacement
        
        # Replace 'a', 'b', 'c' placeholders with random letters/digits
        for i in range(len(uname_chars)):
            if uname_chars[i] in ['a', 'b', 'c']: # Check if the char at current position is a placeholder
                uname_chars[i] = random.choice(letters)
        
        final_uname = "".join(uname_chars) # Join back to string

        # Basic Telegram username validity check before considering
        # Telegram usernames: 5-32 chars, a-z, 0-9, underscores. Must not start with underscore.
        if 5 <= len(final_uname) <= 32 and final_uname[0] != '_' and final_uname.replace('_', '').isalnum():
            generated.add(final_uname)
        attempts += 1
    
    return list(generated)


# Telegram API username availability checker
async def check_username_availability(context: ContextTypes.DEFAULT_TYPE, username: str) -> bool:
    # Full Telegram username rules: 5-32 chars, a-z, 0-9, underscores. Must not start with underscore.
    if not (5 <= len(username) <= 32 and username[0] != '_' and username.replace('_', '').isalnum()):
        logger.warning(f"Invalid username format or length (pre-API check): {username}")
        return False

    try:
        # Attempt to get chat info using the username.
        # If it succeeds without BadRequest, it means a chat (user, bot, channel, group) exists with that username.
        chat = await context.bot.get_chat(f"@{username}")
        
        # If get_chat succeeds and the chat explicitly has that exact username, it's taken.
        if chat.username and chat.username.lower() == username.lower():
            logger.info(f"Username @{username} already exists (get_chat successful). Chat ID: {chat.id}")
            return False
        
        # In some edge cases, get_chat might succeed for private chats without a public username,
        # or for certain bots. Generally, if get_chat doesn't raise BadRequest, it's considered taken.
        return False
    except BadRequest as e:
        error_message = str(e).lower()
        # "username not found" or "chat not found" are primary indicators that the username is available.
        if "username not found" in error_message or "chat not found" in error_message:
            logger.info(f"Username @{username} is likely available (BadRequest: {error_message}).")
            return True
        logger.error(f"Telegram API BadRequest checking username {username}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking username {username}: {e}")

    return False

# Handle generated pattern request
async def ask_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = update.message.text.strip()
    if not pattern:
        await update.message.reply_text("Please provide a valid pattern.", reply_markup=get_stop_and_back_keyboard())
        return ASK_EXAMPLE # Stay in the same state if pattern is empty

    await update.message.reply_text("Searching for available usernames, please wait...", reply_markup=get_stop_and_back_keyboard())
    
    raw_usernames = generate_usernames(pattern, limit=200) # Generate more to increase chances of finding available
    available = []
    
    for uname in raw_usernames:
        if await check_username_availability(context, uname):
            available.append(uname)
            if len(available) >= 20: # Display up to 20 available usernames
                break
        await asyncio.sleep(0.05) # Small delay to prevent hitting Telegram API rate limits (FloodWait)

    if available:
        text = "✅ First 20 available usernames:\n" + "\n".join(available)
    else:
        text = f"😔 No available usernames found for your pattern '{pattern}' after checking {len(raw_usernames)} variations."

    await update.message.reply_text(text, reply_markup=get_stop_and_back_keyboard())
    return ConversationHandler.END # End the conversation for this branch

# Handle bulk checking request
async def bulk_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [n.strip() for n in update.message.text.splitlines() if n.strip()]
    if not names:
        await update.message.reply_text("Please provide a list of usernames.", reply_markup=get_stop_and_back_keyboard())
        return BULK_LIST # Stay in the same state if list is empty

    await update.message.reply_text("Checking your list, please wait...", reply_markup=get_stop_and_back_keyboard())

    available = []
    for name in names:
        if await check_username_availability(context, name):
            available.append(name)
        await asyncio.sleep(0.05) # Small delay to prevent hitting Telegram API rate limits (FloodWait)

    if available:
        text = "✅ Available usernames:\n" + "\n".join(available)
    else:
        text = "😔 None of the provided usernames are available."

    await update.message.reply_text(text, reply_markup=get_stop_and_back_keyboard())
    return ConversationHandler.END # End the conversation for this branch

# Cancel command handler (can be typed by user)
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled. Type /start to begin again.", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END # End the entire conversation

# Main application setup and run
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    # Define the ConversationHandler, which manages the multi-step conversation flow
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)], # Conversation starts when user sends /start
        states={
            # State for the initial menu, waiting for a button click
            INITIAL_MENU: [CallbackQueryHandler(button)], 
            
            # State for generating usernames, expecting text input or specific button clicks
            ASK_EXAMPLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_example), # Handles text input for pattern
                CallbackQueryHandler(button, pattern="^back$|^stop$") # Handles "Back" or "Stop" buttons
            ],
            
            # State for bulk checking, expecting text input (list of usernames) or specific button clicks
            BULK_LIST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_list), # Handles text input for list
                CallbackQueryHandler(button, pattern="^back$|^stop$") # Handles "Back" or "Stop" buttons
            ],
            
            # State for showing "How To" info, expecting specific button clicks to go back
            HOW_TO_INFO: [
                CallbackQueryHandler(button, pattern="^back$|^stop$") # Handles "Back" or "Stop" buttons
            ]
        },
        # Fallbacks handle commands/buttons that can be pressed at any time to exit or change flow
        fallbacks=[
            CommandHandler("cancel", cancel), # /cancel command to end conversation
            CallbackQueryHandler(button, pattern="^back$|^stop$") # Global fallback for back/stop buttons
        ],
        # Set per_message=False for ConversationHandler itself to allow handling callbacks regardless of the message origin
        per_message=False 
    )

    # Add the ConversationHandler to the application. All other handlers are now managed by it.
    app.add_handler(conv_handler)

    # Webhook or Polling configuration based on environment variables
    PORT = int(os.getenv("PORT", "8080")) # Default port for Railway
    WEBHOOK_URL = os.getenv("WEBHOOK_URL") # This should be set in Railway (e.g., https://your-app-name.railway.app)
    
    # This line attempts to get WEBHOOK_SECRET_PATH from Railway's environment variables.
    # If not set in Railway, it generates a random one (which is undesirable for consistent webhooks).
    WEBHOOK_SECRET_PATH = os.getenv("WEBHOOK_SECRET_PATH", f"webhook_{os.urandom(16).hex()}")
    logger.info(f"DEBUG: WEBHOOK_SECRET_PATH being used: {WEBHOOK_SECRET_PATH}") # <<< DEBUG LINE to confirm what path is being used

    if WEBHOOK_URL:
        logger.info(f"Starting Webhook at {WEBHOOK_URL}/{WEBHOOK_SECRET_PATH} on port {PORT}")
        app.run_webhook(
            listen="0.0.0.0", # Listen on all available network interfaces
            port=PORT, # Port to listen on
            url_path=WEBHOOK_SECRET_PATH, # The unique path Telegram will send updates to
            webhook_url=f"{WEBHOOK_URL}/{WEBHOOK_SECRET_PATH}" # The full URL Telegram needs to know
        )
    else:
        logger.warning("No WEBHOOK_URL set. Running in polling mode. This is not recommended for production on Railway.")
        app.run_polling() # Fallback to polling mode for local testing if WEBHOOK_URL is not set
