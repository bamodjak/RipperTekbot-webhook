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

# Telegram file size limits for documents
TELEGRAM_FILE_LIMIT_MB = 50
# Safe chunk size (e.g., 95% of 50 MB to account for overhead)
SAFE_CHUNK_SIZE_BYTES = int(TELEGRAM_FILE_LIMIT_MB * 0.95 * 1024 * 1024) 

# Number of lines to send as text preview before sending the actual file(s)
PREVIEW_MESSAGE_LINES = 10

# --- Conversation States ---
GET_PATTERN = 1
GET_PREFIX_CHOICE = 2
# (No new state for deduplication, as it's an optional argument for now)

# --- Helper Functions ---
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
        if total_combinations > 10**18: total_combinations = 10**18 
             
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

def format_bytes(bytes_num):
    if bytes_num == 0: return '0 Bytes'
    k = 1024
    sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
    i = math.floor(math.log(bytes_num) / math.log(k))
    return f"{bytes_num / (k ** i):.2f} {sizes[i]}"

def generate_combinations(
    pattern: str, 
    output_file_path: str, 
    prefix_type: str = 'none',
    deduplicate_case_insensitive: bool = False # New parameter for deduplication
):
    """
    Generates combinations based on the pattern and saves them to the specified file.
    Includes optional case-insensitive deduplication.
    """
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
    generated_count = 0 # This will be the count of actual lines written
    
    seen_words_lower = set() if deduplicate_case_insensitive else None # Initialize set only if needed

    with open(output_file_path, 'w', encoding='utf-8') as f:
        for i in range(total_combinations): # Loop through all theoretical combinations
            prefix = _get_prefix_char(i, total_combinations, prefix_type)
            base_word_chars = [var_sets[j][idx] for j, idx in enumerate(indices)]
            word = prefix + "".join(base_word_chars)

            if deduplicate_case_insensitive:
                current_word_lower = word.lower()
                if current_word_lower not in seen_words_lower: # Check for uniqueness
                    seen_words_lower.add(current_word_lower)
                    f.write(word + '\n')
                    generated_count += 1 # Only count unique words
            else:
                f.write(word + '\n')
                generated_count += 1 # Count all words

            # Update indices for the next combination (always update, regardless of duplication)
            for j in range(len(var_sets) - 1, -1, -1):
                if indices[j] + 1 < len(var_sets[j]): indices[j] += 1; break
                else: indices[j] = 0
    return generated_count

# --- File Splitting and Sending Function ---
async def split_and_send_file(
    file_path: str,
    chat_id: int,
    bot: Application.bot, 
    original_message_id: int 
):
    file_size = os.path.getsize(file_path)
    
    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=original_message_id,
        text=f"File is too large ({format_bytes(file_size)}), splitting and sending in parts..."
    )

    part_num = 1
    total_parts_estimate = math.ceil(file_size / SAFE_CHUNK_SIZE_BYTES) 
    
    temp_file_base = f"temp_chunk_{os.path.basename(file_path).replace('.txt', '')}_{os.urandom(4).hex()}"
    temp_files_created = []

    try:
        with open(file_path, 'r', encoding='utf-8') as infile:
            current_chunk_lines = []
            current_chunk_size_bytes = 0

            for line in infile:
                line_bytes = line.encode('utf-8')
                
                if current_chunk_size_bytes + len(line_bytes) > SAFE_CHUNK_SIZE_BYTES and current_chunk_lines:
                    temp_chunk_path = os.path.join(GENERATED_FILES_DIR, f"{temp_file_base}_part_{part_num}.txt")
                    with open(temp_chunk_path, 'w', encoding='utf-8') as outfile:
                        outfile.write("".join(current_chunk_lines))
                    temp_files_created.append(temp_chunk_path)

                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=original_message_id,
                        text=f"Sending part {part_num} of (approx. {total_parts_estimate})..."
                    )
                    
                    with open(temp_chunk_path, 'rb') as f:
                        await bot.send_document(
                            chat_id=chat_id,
                            document=f, 
                            filename=f"{Path(file_path).stem}_part_{part_num}.txt",
                            caption=f"Part {part_num} (Original: {Path(file_path).name})"
                        )
                    
                    current_chunk_lines = [line]
                    current_chunk_size_bytes = len(line_bytes)
                    part_num += 1
                else:
                    current_chunk_lines.append(line)
                    current_chunk_size_bytes += len(line_bytes)
            
            if current_chunk_lines:
                temp_chunk_path = os.path.join(GENERATED_FILES_DIR, f"{temp_file_base}_part_{part_num}.txt")
                with open(temp_chunk_path, 'w', encoding='utf-8') as outfile:
                    outfile.write("".join(current_chunk_lines))
                temp_files_created.append(temp_chunk_path)
                
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=original_message_id,
                    text=f"Sending final part {part_num} of (approx. {total_parts_estimate})..."
                )
                with open(temp_chunk_path, 'rb') as f:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=f, 
                        filename=f"{Path(file_path).stem}_part_{part_num}.txt",
                        caption=f"Part {part_num} (Original: {Path(file_path).name})"
                    )
                part_num += 1 

        final_message = f"✅ Successfully sent {part_num - 1} parts of the file (original size: {format_bytes(file_size)})."
        if part_num - 1 == 0: 
            final_message = f"Generated file was empty or too small to split meaningfully. No parts sent."

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=original_message_id,
            text=final_message
        )
    except Exception as e:
        print(f"Error during file splitting or sending: {e}", exc_info=True)
        await bot.send_message( 
            chat_id=chat_id,
            text=f"An error occurred while splitting/sending the file: {e}"
        )
    finally:
        for temp_file in temp_files_created:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                print(f"Cleaned up temporary chunk file: {temp_file}")
        if os.path.exists(file_path): 
            os.remove(file_path)
            print(f"Cleaned up main generated file: {file_path}")


# --- Telegram Bot Handlers ---

# Define the custom Reply Keyboard (always on display)
REPLY_KEYBOARD_MARKUP = ReplyKeyboardMarkup(
    [[KeyboardButton("🏠 Generate Pattern"), KeyboardButton("❓ Help")]], 
    resize_keyboard=True, 
    one_time_keyboard=False 
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Sends a message when the command /start is issued and shows the main keyboard."""
    await update.message.reply_text(
        'Hello! I\'m your Pattern Generator Bot. Tap "🏠 Generate Pattern" or send /generate to start!',
        reply_markup=REPLY_KEYBOARD_MARKUP
    )
    return ConversationHandler.END 

async def generate_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Initiates the pattern generation conversation by asking for the pattern."""
    await update.message.reply_text(
        'Please send me the pattern you want to generate (e.g., `Xx"6"x"t"xx`):',
        reply_markup=ReplyKeyboardMarkup([['Cancel']], resize_keyboard=True, one_time_keyboard=True) 
    )
    return GET_PATTERN 

async def get_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the pattern from the user and asks for prefix choice and deduplication."""
    pattern_text = update.message.text
    if pattern_text.lower() == 'cancel':
        await update.message.reply_text("Generation cancelled.", reply_markup=REPLY_KEYBOARD_MARKUP)
        return ConversationHandler.END

    context.user_data['pattern'] = pattern_text 

    # Create inline keyboard for prefix choice AND deduplication option
    keyboard = [
        [InlineKeyboardButton("Line Number (1-N)", callback_data='prefix_lineNumber')],
        [InlineKeyboardButton("Space", callback_data='prefix_space')],
        [InlineKeyboardButton("None (No Prefix)", callback_data='prefix_none')],
        [InlineKeyboardButton("Enable Deduplication", callback_data='dedupe_true')], # New button for dedupe
        [InlineKeyboardButton("Disable Deduplication", callback_data='dedupe_false')], # New button for dedupe
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Choose a prefix type and/or deduplication option:",
        reply_markup=reply_markup
    )
    # Store initial dedupe state as false for this pattern unless selected
    context.user_data['deduplicate_case_insensitive'] = False 
    return GET_PREFIX_CHOICE 

async def handle_prefix_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the prefix choice or deduplication toggle from the inline keyboard."""
    query = update.callback_query
    await query.answer() 
    
    callback_data = query.data
    pattern = context.user_data.get('pattern')

    # Handle prefix choice
    if callback_data.startswith('prefix_'):
        prefix_type_from_callback = callback_data.replace('prefix_', '')
        context.user_data['prefix_type'] = prefix_type_from_callback
        await query.edit_message_text(f"Pattern: `{pattern}`\nPrefix type set to: `{prefix_type_from_callback}`\nChoose deduplication option or Generate:", parse_mode='Markdown', reply_markup=None)
    
    # Handle deduplication choice
    elif callback_data.startswith('dedupe_'):
        dedupe_status = callback_data.replace('dedupe_', '') == 'true'
        context.user_data['deduplicate_case_insensitive'] = dedupe_status
        dedupe_text = "Enabled" if dedupe_status else "Disabled"
        await query.edit_message_text(f"Pattern: `{pattern}`\nDeduplication set to: `{dedupe_text}`\nChoose prefix type or Generate:", parse_mode='Markdown', reply_markup=None)
    
    # Recreate the keyboard for next selection (or final generate)
    current_prefix_type = context.user_data.get('prefix_type', 'none')
    current_dedupe_status = context.user_data.get('deduplicate_case_insensitive', False)
    
    keyboard = [
        [InlineKeyboardButton("Line Number (1-N)", callback_data='prefix_lineNumber')],
        [InlineKeyboardButton("Space", callback_data='prefix_space')],
        [InlineKeyboardButton("None (No Prefix)", callback_data='prefix_none')],
        [InlineKeyboardButton("Enable Deduplication", callback_data='dedupe_true')],
        [InlineKeyboardButton("Disable Deduplication", callback_data='dedupe_false')],
        [InlineKeyboardButton("Generate Pattern Now!", callback_data='generate_final')] # New button to trigger final generation
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        f"Current Settings: Prefix=`{current_prefix_type}`, Dedupe=`{'Enabled' if current_dedupe_status else 'Disabled'}`\nWhat's next?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    # If the final generate button is clicked, trigger the generation process
    if callback_data == 'generate_final':
        return await _execute_generation(update, context)
        
    return GET_PREFIX_CHOICE # Stay in this state to allow multiple choices

async def _execute_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Internal function to execute the generation process after all options are chosen."""
    query = update.callback_query # This will be the generate_final query
    chat_id = query.message.chat_id
    pattern = context.user_data.get('pattern')
    prefix_type_from_callback = context.user_data.get('prefix_type', 'none')
    deduplicate_status = context.user_data.get('deduplicate_case_insensitive', False)

    if not pattern:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=query.message.message_id, text="Error: Pattern not found. Please start over with /generate.", reply_markup=None)
        return ConversationHandler.END

    # Initial message to display generation status, will be edited
    initial_message = await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text="Starting generation...", 
        reply_markup=None # Remove inline keyboard from previous message
    )

    try:
        segments, total_est_combinations, _ = estimate_pattern_characteristics(pattern)
        
        if total_est_combinations == 0:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=initial_message.message_id, text="Error: Pattern yields 0 combinations. Please check your pattern.", reply_markup=None)
            return ConversationHandler.END
        
        # Provide immediate feedback to the user via message edit
        response_text = f"Generating ~{total_est_combinations:,} combinations"
        if prefix_type_from_callback != 'none':
            response_text += f" with prefix type '{prefix_type_from_callback}'"
        if deduplicate_status:
            response_text += " with deduplication enabled"
        response_text += ". This might take a while for large patterns..."
        await context.bot.edit_message_text(chat_id=chat_id, message_id=initial_message.message_id, text=response_text, reply_markup=None)
        
        # Define output file path on the server (actual name on disk)
        sanitized_pattern_name = sanitize_filename(pattern)
        raw_output_file_name = f"{sanitized_pattern_name}_{total_est_combinations}.txt" 
        output_file_path = os.path.join(GENERATED_FILES_DIR, raw_output_file_name)

        # Generate combinations and write directly to file
        generated_count = generate_combinations(pattern, output_file_path, prefix_type_from_callback, deduplicate_case_insensitive=deduplicate_status)
        actual_file_size = os.path.getsize(output_file_path)

        # --- Live Preview (First few lines) ---
        preview_lines_content = []
        if actual_file_size > 0:
            try:
                with open(output_file_path, 'r', encoding='utf-8') as f_preview:
                    for _ in range(PREVIEW_MESSAGE_LINES):
                        line = f_preview.readline()
                        if not line: break 
                        preview_lines_content.append(line)
                
                preview_text = "".join(preview_lines_content)
                if generated_count > PREVIEW_MESSAGE_LINES:
                    preview_text += "...\n(Full file sending)"
                
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=initial_message.message_id, 
                    text=f"Generated preview:\n```\n{preview_text}```", 
                    parse_mode='Markdown'
                )
            except Exception as preview_e:
                print(f"Error generating preview: {preview_e}")
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=initial_message.message_id,
                    text="Generated file, but preview failed. Sending file directly...",
                    reply_markup=None
                )
        else:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=initial_message.message_id,
                text="Generated an empty file. Please check your pattern.",
                reply_markup=None
            )
            if os.path.exists(output_file_path): os.remove(output_file_path)
            await context.bot.send_message(chat_id=chat_id, text="Generated an empty file. Please try again.", reply_markup=REPLY_KEYBOARD_MARKUP)
            return ConversationHandler.END 

        # --- Send Actual File(s) ---
        if actual_file_size > SAFE_CHUNK_SIZE_BYTES:
            await split_and_send_file(
                file_path=output_file_path,
                chat_id=chat_id, 
                bot=context.bot,
                original_message_id=initial_message.message_id 
            )
        else:
            formatted_output_file_name = f"{sanitized_pattern_name}_{generated_count:,}.txt" 
            with open(output_file_path, 'rb') as f: 
                await context.bot.send_document(
                    chat_id=chat_id, 
                    document=f, 
                    filename=formatted_output_file_name, 
                    caption=f"✅ Generated {generated_count:,} combinations for pattern '{pattern}'."
                )
            os.remove(output_file_path) 
            print(f"Cleaned up file: {output_file_path}")
            await initial_message.edit_text("Generation complete!", reply_markup=None)
            await context.bot.send_message(chat_id=chat_id, text="You can generate more patterns or use /start!", reply_markup=REPLY_KEYBOARD_MARKUP)

    except ValueError as ve:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=initial_message.message_id, text=f"Pattern error: {ve}", reply_markup=None)
        print(f"Pattern error for '{pattern}': {ve}")
        await context.bot.send_message(chat_id=chat_id, text="Generation failed. Please try again with /generate.", reply_markup=REPLY_KEYBOARD_MARKUP)
    except Exception as e:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=initial_message.message_id, text=f"An unexpected error occurred during generation: {e}", reply_markup=None)
        print(f"Unexpected error for pattern '{pattern}': {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="Generation failed. Please try again with /generate.", reply_markup=REPLY_KEYBOARD_MARKUP)
    
    return ConversationHandler.END 


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current conversation."""
    await update.message.reply_text("Operation cancelled.", reply_markup=REPLY_KEYBOARD_MARKUP)
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message."""
    help_text = (
        "I'm your Pattern Generator Bot!\n\n"
        "To start generating: Tap '🏠 Generate Pattern' or send /generate.\n\n"
        "Usage:\n"
        "1. Send your pattern (e.g., `Xx\"abc\"X`).\n"
        "   - `X` or `x`: Generates a random letter (A-Z, a-z).\n"
        "   - `\"text\"`: Generates the exact text enclosed in quotes.\n\n"
        "2. Choose options via buttons:\n"
        "   - `Line Number (1-N)`: Adds sequential numbers (1-, 2-, etc.) to each line.\n"
        "   - `Space`: Adds a space to the beginning of each line.\n"
        "   - `None (No Prefix)`: Generates lines without any prefix.\n"
        "   - `Enable/Disable Deduplication`: Removes duplicate words (case-insensitive).\n\n"
        "File Size Limit:\n"
        "  - Telegram limits files to 50 MB. Larger files will be automatically split into multiple parts."
    )
    await update.message.reply_text(help_text, reply_markup=REPLY_KEYBOARD_MARKUP)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends an about message."""
    about_text = (
        "Pattern Generator Bot v1.0\n"
        "Created to generate custom patterns quickly.\n"
        "Supports sequential numbering, spaces, and custom strings.\n"
        "Files over 50MB are split automatically."
    )
    await update.message.reply_text(about_text, reply_markup=REPLY_KEYBOARD_MARKUP)


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
            MessageHandler(filters.Regex("^🏠 Generate Pattern$"), generate_start) 
        ],
        states={
            GET_PATTERN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pattern)],
            GET_PREFIX_CHOICE: [CallbackQueryHandler(handle_prefix_choice)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation), 
            MessageHandler(filters.Regex("^Cancel$"), cancel_conversation), 
            CommandHandler("start", start_command), 
            CommandHandler("help", help_command), # Handle /help as fallback
            CommandHandler("about", about_command), # Handle /about as fallback
            # Add a message handler to catch unexpected input and re-prompt or cancel
            MessageHandler(filters.ALL, cancel_conversation) # Catches all other messages as implicit cancel
        ],
        per_user=True 
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start_command)) 
    application.add_handler(CommandHandler("help", help_command)) 
    application.add_handler(CommandHandler("about", about_command)) 
    
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
