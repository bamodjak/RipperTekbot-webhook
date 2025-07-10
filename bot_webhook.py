import os
import math
import io 
from pathlib import Path
from typing import List, Dict, Any, Generator
import asyncio 

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    ContextTypes, filters, ConversationHandler
)
from telegram.error import BadRequest 

# --- Constants ---
LETTERS = 'abcdefghijklmnopqrstuvwxyz'
NUMBERS = '0123456789'
VALID_CHARS = LETTERS + LETTERS.upper() + NUMBERS
FIRST_CHAR_SET = LETTERS + LETTERS.upper()

# Telegram file size limits for documents
TELEGRAM_FILE_LIMIT_MB = 50
SAFE_CHUNK_SIZE_BYTES = int(TELEGRAM_FILE_LIMIT_MB * 0.95 * 1024 * 1024) 

# Number of lines to send as text preview before sending the actual file(s)
PREVIEW_MESSAGE_LINES = 10

# --- Conversation States ---
GET_PATTERN = 1
GET_PREFIX_CHOICE = 2

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

# --- Modified generate_combinations to be a line generator ---
def generate_combinations_line_iter(
    pattern: str, 
    prefix_type: str = 'none', 
    deduplicate_case_insensitive: bool = False
) -> Generator[str, None, None]:
    """
    Generates combinations as an iterator, yielding individual lines.
    Does not write to disk.
    """
    segments, total_combinations, _ = estimate_pattern_characteristics(pattern)
    
    seen_words_lower = set() if deduplicate_case_insensitive else None
    
    var_sets = []
    first_variable_segment_found = False
    for seg in segments:
        if seg['type'] == 'const': var_sets.append([seg['value']])
        else:
            if not first_variable_segment_found: var_sets.append(list(FIRST_CHAR_SET)); first_variable_found = True
            else: var_sets.append(list(VALID_CHARS))

    indices = [0] * len(var_sets)
    
    for i in range(total_combinations):
        prefix = _get_prefix_char(i, total_combinations, prefix_type)
        base_word_chars = [var_sets[j][idx] for j, idx in enumerate(indices)]
        word = prefix + "".join(base_word_chars)
        line = word + '\n'

        if deduplicate_case_insensitive:
            current_word_lower = word.lower()
            if current_word_lower not in seen_words_lower:
                seen_words_lower.add(current_word_lower)
                yield line # Yield only if unique
        else:
            yield line # Yield all lines

        # Update indices for the next combination
        for j in range(len(var_sets) - 1, -1, -1):
            if indices[j] + 1 < len(var_sets[j]): indices[j] += 1; break
            else: indices[j] = 0

# --- Async Function to Stream and Send File Parts ---
async def send_generated_stream(
    pattern: str, 
    prefix_type: str, 
    deduplicate_case_insensitive: bool,
    chat_id: int, 
    bot: Application.bot, 
    original_message_id: int,
    total_est_combinations: int 
):
    temp_files_created = [] 
    part_num = 1
    total_bytes_sent = 0
    actual_generated_lines_count = 0 

    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=original_message_id,
        text=f"Generating and sending in real-time for ~{total_est_combinations:,} combinations. Please wait for parts..."
    )

    try:
        line_iterator = generate_combinations_line_iter(pattern, prefix_type, deduplicate_case_insensitive)
        
        current_chunk_lines_buffer = []
        current_chunk_size_bytes = 0
        
        preview_lines_list = [] 
        preview_sent = False

        for line in line_iterator: 
            # Check for cancellation before processing each line
            try:
                await asyncio.sleep(0.0001) # Allows asyncio to check for cancellations and yield control
            except asyncio.CancelledError:
                print(f"send_generated_stream was cancelled by command for chat {chat_id}.")
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=original_message_id,
                    text=f"❌ Generation stopped by command. (Generated {actual_generated_lines_count:,} lines, sent {format_bytes(total_bytes_sent)}).",
                    reply_markup=None
                )
                raise # Re-raise to propagate cancellation and skip further processing

            actual_generated_lines_count += 1
            line_bytes = line.encode('utf-8')

            # --- Handle Live Preview ---
            if not preview_sent and len(preview_lines_list) < PREVIEW_MESSAGE_LINES:
                preview_lines_list.append(line)
                if len(preview_lines_list) == PREVIEW_MESSAGE_LINES: 
                    preview_text_content = "".join(preview_lines_list)
                    if actual_generated_lines_count < total_est_combinations: 
                        preview_text_content += "...\n(Full file sending in parts)"
                    
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=original_message_id,
                        text=f"Generated preview:\n```\n{preview_text_content}```",
                        parse_mode='Markdown'
                    )
                    preview_sent = True 
            
            current_chunk_lines_buffer.append(line)
            current_chunk_size_bytes += len(line_bytes)

            # --- Check for Chunk Completion and Send ---
            if current_chunk_size_bytes >= SAFE_CHUNK_SIZE_BYTES:
                temp_chunk_path = os.path.join(GENERATED_FILES_DIR, f"chunk_{os.urandom(4).hex()}.txt")
                temp_files_created.append(temp_chunk_path)
                with open(temp_chunk_path, 'w', encoding='utf-8') as f_chunk:
                    f_chunk.write("".join(current_chunk_lines_buffer))
                
                total_bytes_sent += current_chunk_size_bytes
                
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=original_message_id,
                    text=f"Sending part {part_num} (Total sent: {format_bytes(total_bytes_sent)})..."
                )
                
                with open(temp_chunk_path, 'rb') as f_send:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=f_send, 
                        filename=f"{sanitize_filename(pattern)}_{actual_generated_lines_count:,}_part_{part_num}.txt", 
                        caption=f"Part {part_num} (Generated: {actual_generated_lines_count:,} lines)"
                    )
                
                os.remove(temp_chunk_path) 
                temp_files_created.pop() 
                
                current_chunk_lines_buffer = []
                current_chunk_size_bytes = 0
                part_num += 1

        # --- Send Any Remaining Data in the Last Chunk ---
        if current_chunk_lines_buffer:
            temp_chunk_path = os.path.join(GENERATED_FILES_DIR, f"chunk_final_{os.urandom(4).hex()}.txt") 
            temp_files_created.append(temp_chunk_path)
            with open(temp_chunk_path, 'w', encoding='utf-8') as f_chunk:
                f_chunk.write("".join(current_chunk_lines_buffer))
            
            total_bytes_sent += current_chunk_size_bytes

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=original_message_id,
                text=f"Sending final part {part_num} (Total sent: {format_bytes(total_bytes_sent)})..."
            )

            with open(temp_chunk_path, 'rb') as f_send:
                await bot.send_document(
                    chat_id=chat_id,
                    document=f_send, 
                    filename=f"{sanitize_filename(pattern)}_{actual_generated_lines_count:,}_final_part_{part_num}.txt", 
                    caption=f"Part {part_num} (Generated: {actual_generated_lines_count:,} lines)"
                )
            part_num += 1
            os.remove(temp_chunk_path)
            temp_files_created.pop()

        # --- Final Status Message ---
        final_message_text = f"✅ Generation and delivery complete! Total parts sent: {part_num - 1}. Total generated unique lines: {actual_generated_lines_count:,}. Final size: {format_bytes(total_bytes_sent)}."
        if actual_generated_lines_count == 0:
            final_message_text = "Generated file was empty. Please check your pattern or deduplication settings."

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=original_message_id,
            text=final_message_text
        )

    except Exception as e: # Catch any other exceptions during generation/sending
        print(f"Error during streamed generation/sending: {e}", exc_info=True)
        # Check if the message can still be edited, if not, send a new one
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=original_message_id,
                text=f"❌ An error occurred during generation/delivery: {e}",
                reply_markup=None # Ensure no inline keyboard remains
            )
        except Exception:
            await bot.send_message( # Send new message if edit fails
                chat_id=chat_id,
                text=f"❌ An error occurred during generation/delivery: {e}",
                reply_markup=None
            )
    finally:
        # Ensure all temporary files are cleaned up in case of error or cancellation
        for temp_file in temp_files_created:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                print(f"Cleaned up temporary chunk file in finally: {temp_file}")
        # Send a final 'bot ready' message and show main keyboard
        await bot.send_message(chat_id=chat_id, text="Bot is ready for your next command!", reply_markup=REPLY_KEYBOARD_MARKUP)


# --- Telegram Bot Handlers ---

# Define the custom Reply Keyboard (always on display)
REPLY_KEYBOARD_MARKUP = ReplyKeyboardMarkup(
    [[KeyboardButton("🏠 Generate Pattern"), KeyboardButton("⏹ Stop"), KeyboardButton("❓ Help")]], 
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
    
    # NEW FIX: If the user sends the button text as pattern, ignore and re-prompt
    if pattern_text == "🏠 Generate Pattern" or pattern_text == "🏠Generate Pattern": # Account for potential no-space formatting
        await update.message.reply_text(
            "I received the 'Generate Pattern' button tap. Please *type and send* your actual pattern now (e.g., `Xx\"6\"x\"t\"xx`):",
            reply_markup=ReplyKeyboardMarkup([['Cancel']], resize_keyboard=True, one_time_keyboard=True)
        )
        return GET_PATTERN # Stay in GET_PATTERN state, don't store pattern

    context.user_data['pattern'] = pattern_text 

    # Create inline keyboard for prefix choice AND deduplication option
    keyboard = [
        [InlineKeyboardButton("Line Number (1-N)", callback_data='prefix_lineNumber')],
        [InlineKeyboardButton("Space", callback_data='prefix_space')],
        [InlineKeyboardButton("None (No Prefix)", callback_data='prefix_none')],
        [InlineKeyboardButton("Enable Deduplication", callback_data='dedupe_true')], 
        [InlineKeyboardButton("Disable Deduplication", callback_data='dedupe_false')], 
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Choose a prefix type and/or deduplication option:",
        reply_markup=reply_markup
    )
    # Store initial dedupe state as false for this pattern unless explicitly enabled
    context.user_data['deduplicate_case_insensitive'] = False 
    context.user_data['prefix_type'] = 'none' # Store initial prefix type as default 'none'
    return GET_PREFIX_CHOICE 

async def handle_prefix_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the prefix choice or deduplication toggle from the inline keyboard."""
    query = update.callback_query
    await query.answer() 
    
    callback_data = query.data
    pattern = context.user_data.get('pattern')

    # If the final generate button is clicked, trigger the generation process
    if callback_data == 'generate_final':
        return await _execute_generation(update, context)

    # Handle prefix choice
    if callback_data.startswith('prefix_'):
        prefix_type_from_callback = callback_data.replace('prefix_', '')
        context.user_data['prefix_type'] = prefix_type_from_callback
        
    # Handle deduplication choice
    elif callback_data.startswith('dedupe_'):
        dedupe_status = callback_data.replace('dedupe_', '') == 'true'
        context.user_data['deduplicate_case_insensitive'] = dedupe_status
        
    # Recreate the keyboard with updated selections for next choice or final generate
    current_prefix_type = context.user_data.get('prefix_type', 'none')
    current_dedupe_status = context.user_data.get('deduplicate_case_insensitive', False)
    
    keyboard = [
        [InlineKeyboardButton(f"Prefix: {'Line Number' if current_prefix_type == 'lineNumber' else ('Space' if current_prefix_type == 'space' else 'None')}", callback_data='dummy')], 
        [InlineKeyboardButton("Line Number (1-N)", callback_data='prefix_lineNumber')],
        [InlineKeyboardButton("Space", callback_data='prefix_space')],
        [InlineKeyboardButton("None (No Prefix)", callback_data='prefix_none')],
        [InlineKeyboardButton(f"Dedupe: {'Enabled' if current_dedupe_status else 'Disabled'}", callback_data='dummy')], 
        [InlineKeyboardButton("Enable Deduplication", callback_data='dedupe_true')],
        [InlineKeyboardButton("Disable Deduplication", callback_data='dedupe_false')],
        [InlineKeyboardButton("Generate Pattern Now!", callback_data='generate_final')] 
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Edit the current message with updated settings and keyboard
    try:
        await query.edit_message_text(
            f"Pattern: `{pattern}`\nCurrent Settings: Prefix=`{current_prefix_type}`, Dedupe=`{'Enabled' if current_dedupe_status else 'Disabled'}`\nSelect again or Generate:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            print(f"DEBUG: Message not modified, skipping edit: {e}")
        else:
            raise # Re-raise other BadRequest errors
        
    return GET_PREFIX_CHOICE 

async def _execute_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Internal function to execute the generation process after all options are chosen."""
    query = update.callback_query 
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
        reply_markup=None 
    )
    
    # Store the generation task in user_data for potential cancellation
    total_est_combinations_for_task = (estimate_pattern_characteristics(pattern))[1]
    task_args = {
        'pattern': pattern,
        'prefix_type': prefix_type_from_callback,
        'deduplicate_case_insensitive': deduplicate_status,
        'chat_id': chat_id,
        'bot': context.bot,
        'original_message_id': initial_message.message_id,
        'total_est_combinations': total_est_combinations_for_task
    }
    context.user_data['current_generation_task'] = asyncio.create_task(send_generated_stream(**task_args))

    try:
        await context.user_data['current_generation_task'] 
    except asyncio.CancelledError:
        print(f"Generation task for chat {chat_id} was explicitly cancelled in _execute_generation.")
    except Exception as e:
        print(f"Unhandled exception in _execute_generation for pattern '{pattern}': {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="An unexpected error occurred. Please try again.", reply_markup=REPLY_KEYBOARD_MARKUP)
    finally:
        if 'current_generation_task' in context.user_data:
            del context.user_data['current_generation_task']

    return ConversationHandler.END 

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current conversation."""
    task = context.user_data.get('current_generation_task')
    if task:
        task.cancel()
        await update.message.reply_text("Generation stop requested. Please wait for current operation to cease.", reply_markup=REPLY_KEYBOARD_MARKUP)
    else:
        await update.message.reply_text("Operation cancelled (no active generation).", reply_markup=REPLY_KEYBOARD_MARKUP)
    return ConversationHandler.END

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stops an ongoing generation."""
    return await cancel_conversation(update, context) 

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
        "Live Progress:\n"
        "  - For long generations, I'll send parts of the file as soon as they reach ~45MB.\n"
        "  - You'll see a preview of the first few lines and progress updates.\n\n"
        "File Size Limit:\n"
        "  - Telegram limits files to 50 MB. Larger files are automatically split."
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
            CommandHandler("start", start_command), # Allow /start to reset conversation
            CommandHandler("help", help_command), # Allow /help to reset conversation
            CommandHandler("about", about_command), # Allow /about to reset conversation
            CommandHandler("stop", stop_command), # Allow /stop to reset conversation
            MessageHandler(filters.ALL, cancel_conversation) # Catch all other messages as implicit cancel/fallback
        ],
        per_user=True 
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start_command)) 
    application.add_handler(CommandHandler("help", help_command)) 
    application.add_handler(CommandHandler("about", about_command)) 
    application.add_handler(CommandHandler("stop", stop_command)) 
    
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
