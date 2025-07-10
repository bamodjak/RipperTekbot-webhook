import os
import math
from pathlib import Path
from typing import List, Dict, Any

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    ContextTypes, filters, ConversationHandler
)

# --- Constants ---
LETTERS = 'abcdefghijklmnopqrstuvwxyz'
NUMBERS = '0123456789'
VALID_CHARS = LETTERS + LETTERS.upper() + NUMBERS
FIRST_CHAR_SET = LETTERS + LETTERS.upper()

# --- Conversation States ---
GET_PATTERN = 1
GET_PREFIX_CHOICE = 2

# --- Helper Functions (Same as before) ---
def parse_pattern(pattern: str) -> List[Dict[str, str]]:
    segments = []
    in_quote = False
    buf = ""
    for char in pattern:
        if char == '"':
            if in_quote: segments.append({"type": "const", "value": buf}); buf = ""
            in_quote = not in_quote
        elif in_quote: buf += char
        elif char in ['x', 'X']:
            if buf: raise ValueError(f"Malformed pattern: unexpected characters '{buf}' before x/X.")
            segments.append({"type": "var"})
        else: raise ValueError(f"Malformed pattern: invalid character '{char}' detected outside quotes.")
    if in_quote: raise ValueError("Malformed pattern: Unclosed quote (missing \")\").")
    if buf: raise ValueError(f"Malformed pattern: Trailing characters '{buf}' after pattern end.")
    return segments

def estimate_pattern_characteristics(pattern: str) -> (List[Dict[str, Any]], int, int):
    segments = parse_pattern(pattern)
    total_combinations = 1
    estimated_line_char_length = 0
    first_variable_found_in_estimation = False
    
    for seg in segments:
        if seg['type'] == 'const': estimated_line_char_length += len(seg['value'])
        else:
            estimated_line_char_length += 1
            if not first_variable_found_in_estimation: total_combinations *= len(FIRST_CHAR_SET); first_variable_found_in_estimation = True
            else: total_combinations *= len(VALID_CHARS)
        if total_combinations > 10**18: total_combinations = 10**18 # Cap for practical purposes
             
    estimated_line_char_length += 1 # Newline character
    return segments, total_combinations, estimated_line_char_length

def _get_prefix_char(index: int, total_combinations: int, prefix_type: str) -> str:
    if prefix_type == 'lineNumber': return f"{index + 1}- "
    elif prefix_type == 'space': return " "
    elif prefix_type == 'none': return ""
    else: return ""

def sanitize_filename(name: str) -> str:
    sanitized = name.replace('<', '_').replace('>', '_').replace(':', '_').replace('"', '_').replace('/', '_').replace('\\', '_').replace('|', '_').replace('?', '_').replace('*', '_')
    sanitized = sanitized.replace(' ', '_').strip('_').replace('__', '_')
    if len(sanitized) > 50: sanitized = sanitized[:50] + '_etc'
    return sanitized or 'pattern_output'

def generate_combinations(pattern: str, output_file_path: str, prefix_type: str = 'none'):
    segments, total_combinations, _ = estimate_pattern_characteristics(pattern)
    output_path = Path(output_file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    var_sets = []
    first_variable_segment_found = False
    for seg in segments:
        if seg['type'] == 'const': var_sets.append([seg['value']])
        else:
            if not first_variable_segment_found: var_sets.append(list(FIRST_CHAR_SET)); first_variable_segment_found = True
            else: var_sets.append(list(VALID_CHARS))

    indices = [0] * len(var_sets)
    generated_count = 0

    with open(output_file_path, 'w', encoding='utf-8') as f:
        for i in range(total_combinations):
            prefix = _get_prefix_char(i, total_combinations, prefix_type)
            base_word_chars = [var_sets[j][idx] for j, idx in enumerate(indices)]
            word = prefix + "".join(base_word_chars)
            f.write(word + '\n')
            generated_count += 1
            for j in range(len(var_sets) - 1, -1, -1):
                if indices[j] + 1 < len(var_sets[j]): indices[j] += 1; break
                else: indices[j] = 0
    return generated_count

# --- Telegram Bot Handlers ---

# Define the custom Reply Keyboard
# It will have a single button for "Generate Pattern" or "Home" functionality
REPLY_KEYBOARD_MARKUP = ReplyKeyboardMarkup(
    [[KeyboardButton("🏠 Generate Pattern")]],
    resize_keyboard=True, # Makes the keyboard smaller/fit to content
    one_time_keyboard=False # Keeps the keyboard visible
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Sends a message when the command /start is issued and shows the main keyboard."""
    await update.message.reply_text(
        'Hello! I\'m your Pattern Generator Bot. Tap "🏠 Generate Pattern" or send /generate to start!',
        reply_markup=REPLY_KEYBOARD_MARKUP
    )
    return ConversationHandler.END # End any ongoing conversation

async def generate_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Initiates the pattern generation conversation by asking for the pattern."""
    await update.message.reply_text(
        'Please send me the pattern you want to generate (e.g., `Xx"6"x"t"xx`):',
        reply_markup=ReplyKeyboardMarkup([['Cancel']], resize_keyboard=True, one_time_keyboard=True) # Offer a cancel option
    )
    return GET_PATTERN # Move to the GET_PATTERN state

async def get_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the pattern from the user and asks for prefix choice."""
    pattern_text = update.message.text
    if pattern_text.lower() == 'cancel':
        await update.message.reply_text("Generation cancelled.", reply_markup=REPLY_KEYBOARD_MARKUP)
        return ConversationHandler.END

    context.user_data['pattern'] = pattern_text # Store pattern for later use

    # Create inline keyboard for prefix choice
    keyboard = [
        [InlineKeyboardButton("Line Number (1-N)", callback_data='prefix_lineNumber')],
        [InlineKeyboardButton("Space", callback_data='prefix_space')],
        [InlineKeyboardButton("None (No Prefix)", callback_data='prefix_none')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Now, choose a prefix type:",
        reply_markup=reply_markup
    )
    return GET_PREFIX_CHOICE # Move to the GET_PREFIX_CHOICE state

async def handle_prefix_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the prefix choice from the inline keyboard and triggers generation."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback query to remove "loading" spinner
    
    prefix_type_from_callback = query.data.replace('prefix_', '') # Extract 'lineNumber', 'space', 'none'
    pattern = context.user_data.get('pattern')

    if not pattern:
        await query.edit_message_text("Error: Pattern not found. Please start over with /generate.", reply_markup=None)
        return ConversationHandler.END

    try:
        # Estimate total combinations first for user feedback
        segments, total_est_combinations, _ = estimate_pattern_characteristics(pattern)
        
        if total_est_combinations == 0:
            await query.edit_message_text("Error: Pattern yields 0 combinations. Please check your pattern.", reply_markup=None)
            return ConversationHandler.END
        
        # Provide immediate feedback to the user via message edit
        response_text = f"Generating ~{total_est_combinations:,} combinations"
        if prefix_type_from_callback != 'none':
            response_text += f" with prefix type '{prefix_type_from_callback}'"
        response_text += ". This might take a while for large patterns..."
        await query.edit_message_text(response_text, reply_markup=None) # Remove inline keyboard

        # Define output file path on the server
        sanitized_pattern_name = sanitize_filename(pattern)
        output_file_name = f"{sanitized_pattern_name}_{total_est_combinations:,}.txt"
        output_file_path = os.path.join(GENERATED_FILES_DIR, output_file_name)

        # Generate combinations and write directly to file
        generated_count = generate_combinations(pattern, output_file_path, prefix_type_from_callback)

        # Send the generated file back to the user
        with open(output_file_path, 'rb') as f: # Open in binary read mode
            await context.bot.send_document(
                chat_id=query.message.chat_id, 
                document=f, 
                filename=output_file_name, 
                caption=f"✅ Generated {generated_count:,} combinations for pattern '{pattern}'."
            )

        # Clean up the temporary file from the server
        os.remove(output_file_path)
        print(f"Cleaned up file: {output_file_path}")
        await query.message.reply_text("Generation complete!", reply_markup=REPLY_KEYBOARD_MARKUP) # Show main keyboard again

    except ValueError as ve:
        await query.edit_message_text(f"Pattern error: {ve}", reply_markup=None)
        print(f"Pattern error for '{pattern}': {ve}")
        await query.message.reply_text("Generation failed. Please try again with /generate.", reply_markup=REPLY_KEYBOARD_MARKUP)
    except Exception as e:
        await query.edit_message_text(f"An unexpected error occurred during generation: {e}", reply_markup=None)
        # Log the full error on your server side for debugging
        print(f"Unexpected error for pattern '{pattern}': {e}", exc_info=True)
        await query.message.reply_text("Generation failed. Please try again with /generate.", reply_markup=REPLY_KEYBOARD_MARKUP)
    
    return ConversationHandler.END # End the conversation

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current conversation."""
    await update.message.reply_text("Operation cancelled.", reply_markup=REPLY_KEYBOARD_MARKUP)
    return ConversationHandler.END


# --- Main Bot Setup ---
GENERATED_FILES_DIR = "bot_generated_files"
os.makedirs(GENERATED_FILES_DIR, exist_ok=True) 

def main():
    """Starts the bot."""
    bot_token = os.environ.get("TELEGRAM_BOT")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT environment variable not set. Please configure it on Railway.app.")
    
    application = Application.builder().token(bot_token).build()

    # Conversation Handler for multi-step input
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("generate", generate_start),
            MessageHandler(filters.Regex("^🏠 Generate Pattern$"), generate_start) # Handle button tap
        ],
        states={
            GET_PATTERN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pattern)],
            GET_PREFIX_CHOICE: [CallbackQueryHandler(handle_prefix_choice)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation), # /cancel during any state
            MessageHandler(filters.Regex("^Cancel$"), cancel_conversation), # Button for cancel
            CommandHandler("start", start_command) # Allow /start to reset
        ],
        per_user=True # Ensures separate conversations per user
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start_command)) # Make /start always available
    
    # Error handler (optional, but good for catching unhandled exceptions)
    # application.add_error_handler(error_handler) # Uncomment and define if needed

    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
