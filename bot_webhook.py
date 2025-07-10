import os
import math
from pathlib import Path
from typing import List, Dict, Any

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Constants ---
LETTERS = 'abcdefghijklmnopqrstuvwxyz'
NUMBERS = '0123456789'
VALID_CHARS = LETTERS + LETTERS.upper() + NUMBERS
FIRST_CHAR_SET = LETTERS + LETTERS.upper()

# --- Helper Functions ---

def parse_pattern(pattern: str) -> List[Dict[str, str]]:
    """
    Parses a pattern string into segments (e.g., 'x', 'X', '"constant"').
    Translated from JavaScript's parsePattern.
    """
    segments = []
    in_quote = False
    buf = ""
    
    for char in pattern:
        if char == '"':
            if in_quote: # Closing quote
                segments.append({"type": "const", "value": buf})
                buf = ""
            in_quote = not in_quote
        elif in_quote:
            buf += char
        elif char in ['x', 'X']:
            if buf: # Non-empty buffer outside quotes before x/X is an error
                raise ValueError(f"Malformed pattern: unexpected characters '{buf}' before x/X.")
            segments.append({"type": "var"})
        else: # Character outside quotes that is not x, X, or "
            raise ValueError(f"Malformed pattern: invalid character '{char}' detected outside quotes.")
    
    if in_quote:
        raise ValueError("Malformed pattern: Unclosed quote (missing \")\").")
    if buf: # Trailing characters after pattern end
        raise ValueError(f"Malformed pattern: Trailing characters '{buf}' after pattern end.")
    
    return segments

def estimate_pattern_characteristics(pattern: str) -> (List[Dict[str, Any]], int, int):
    """
    Estimates total combinations and character length of a single line.
    Returns (segments, total_combinations, estimated_line_char_length).
    Translated from JavaScript's estimatePatternCharacteristics.
    """
    segments = parse_pattern(pattern)
    total_combinations = 1
    estimated_line_char_length = 0

    first_variable_found_in_estimation = False

    for seg in segments:
        if seg['type'] == 'const':
            estimated_line_char_length += len(seg['value'])
        else: # type == 'var'
            estimated_line_char_length += 1 # Each x/X is 1 character in the word
            if not first_variable_found_in_estimation:
                total_combinations *= len(FIRST_CHAR_SET)
                first_variable_found_in_estimation = True
            else:
                total_combinations *= len(VALID_CHARS)
        
        if total_combinations > 10**18: # Cap at 10^18 for practical purposes
             total_combinations = 10**18
             
    estimated_line_char_length += 1 # Add 1 for the newline character
    
    return segments, total_combinations, estimated_line_char_length


def _get_prefix_char(index: int, total_combinations: int, prefix_type: str) -> str:
    """
    Determines the prefix character/string for a given word based on prefix_type.
    """
    if prefix_type == 'lineNumber':
        return f"{index + 1}- "
    elif prefix_type == 'space':
        return " "
    elif prefix_type == 'none': # Explicitly no prefix
        return "" 
    else:
        return "" # Fallback to no prefix for unknown types

def sanitize_filename(name: str) -> str:
    """
    Sanitizes a string to be safe for use as a filename.
    Translated from JavaScript's sanitizeFilename.
    """
    sanitized = name.replace('<', '_').replace('>', '_') \
                      .replace(':', '_').replace('"', '_') \
                      .replace('/', '_').replace('\\', '_') \
                      .replace('|', '_').replace('?', '_') \
                      .replace('*', '_')
    sanitized = sanitized.replace(' ', '_')
    sanitized = sanitized.strip('_') # Remove leading/trailing underscores
    sanitized = sanitized.replace('__', '_') # Collapse multiple underscores
    
    if len(sanitized) > 50: # Limit length to avoid OS issues
        sanitized = sanitized[:50] + '_etc'
    
    return sanitized or 'pattern_output' # Fallback if empty

def generate_combinations(pattern: str, output_file_path: str, prefix_type: str = 'none'):
    """
    Generates combinations based on the pattern and saves them to the specified file.
    This is the core generation logic, optimized for server-side.
    """
    segments, total_combinations, _ = estimate_pattern_characteristics(pattern)

    # Ensure output directory exists
    output_path = Path(output_file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    var_sets = []
    first_variable_segment_found = False
    for seg in segments:
        if seg['type'] == 'const':
            var_sets.append([seg['value']])
        else:
            if not first_variable_segment_found:
                var_sets.append(list(FIRST_CHAR_SET))
                first_variable_segment_found = True
            else:
                var_sets.append(list(VALID_CHARS))

    indices = [0] * len(var_sets)
    generated_count = 0

    with open(output_file_path, 'w', encoding='utf-8') as f:
        for i in range(total_combinations):
            # Build word
            prefix = _get_prefix_char(i, total_combinations, prefix_type)
            base_word_chars = [var_sets[j][idx] for j, idx in enumerate(indices)]
            word = prefix + "".join(base_word_chars)
            f.write(word + '\n')
            generated_count += 1

            # Update indices for the next combination
            for j in range(len(var_sets) - 1, -1, -1):
                if indices[j] + 1 < len(var_sets[j]):
                    indices[j] += 1
                    break
                else:
                    indices[j] = 0 # Reset this index if it overflowed
    return generated_count

# --- Telegram Bot Integration ---

# Define a directory for generated files on your server
GENERATED_FILES_DIR = "bot_generated_files"
os.makedirs(GENERATED_FILES_DIR, exist_ok=True) # Ensure it exists when bot starts

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message when the command /start is issued."""
    await update.message.reply_text(
        'Hello! Send /generate <pattern> to create combinations.\n'
        'Example: `/generate Xx"6"x"t"xx`\n\n'
        'You can also add a prefix:\n'
        '  - Line Numbers: `/generate Xxxx ln`\n'
        '  - Space: `/generate Xxxx sp`\n'
        '  - No Prefix (default): `/generate Xxxx none`'
    )

async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates patterns and sends the file to the user."""
    if not context.args:
        await update.message.reply_text(
            'Please provide a pattern. Example: `/generate Xx"6"x"t"xx`'
        )
        return

    # Extract pattern and prefix type from arguments
    args = list(context.args) # Make a mutable copy
    pattern_parts = []
    prefix_type = 'none' # Default prefix type
    
    # Check for prefix type argument (e.g., 'ln', 'sp', 'none')
    if args and args[-1] in ['ln', 'sp', 'none']:
        prefix_type_arg = args.pop() # Remove prefix arg from pattern parts
        if prefix_type_arg == 'ln':
            prefix_type = 'lineNumber'
        elif prefix_type_arg == 'sp':
            prefix_type = 'space'
        elif prefix_type_arg == 'none':
            prefix_type = 'none' # Explicitly no prefix

    pattern = " ".join(args) # The rest is the pattern

    if not pattern:
        await update.message.reply_text(
            'Please provide a pattern. Example: `/generate Xx"6"x"t"xx`'
        )
        return

    try:
        # Estimate total combinations first for user feedback
        _, total_est_combinations, _ = estimate_pattern_characteristics(pattern)
        
        if total_est_combinations == 0:
            await update.message.reply_text("Error: Pattern yields 0 combinations. Please check your pattern.")
            return
        
        # Provide feedback to the user immediately
        response_text = f"Generating ~{total_est_combinations:,} combinations"
        if prefix_type != 'none':
            response_text += f" with prefix type '{prefix_type}'"
        response_text += ". This might take a while for large patterns."
        await update.message.reply_text(response_text)

        # Define output file path on the server
        sanitized_pattern_name = sanitize_filename(pattern)
        output_file_name = f"{sanitized_pattern_name}_{total_est_combinations:,}.txt"
        output_file_path = os.path.join(GENERATED_FILES_DIR, output_file_name)

        # Generate combinations and write directly to file
        generated_count = generate_combinations(pattern, output_file_path, prefix_type)

        # Send the generated file back to the user
        with open(output_file_path, 'rb') as f: # Open in binary read mode
            await update.message.reply_document(
                document=f, 
                filename=output_file_name, 
                caption=f"✅ Generated {generated_count:,} combinations for pattern '{pattern}'."
            )

        # Clean up the temporary file from the server
        os.remove(output_file_path)
        print(f"Cleaned up file: {output_file_path}")

    except ValueError as ve:
        await update.message.reply_text(f"Pattern error: {ve}")
        print(f"Pattern error for '{pattern}': {ve}")
    except Exception as e:
        await update.message.reply_text(f"An unexpected error occurred during generation: {e}")
        # Log the full error on your server side for debugging
        print(f"Unexpected error for pattern '{pattern}': {e}", exc_info=True)


def main():
    """Starts the bot."""
    # Create the Application and pass your bot's token.
    # Read the bot token from the environment variable (as configured on Railway.app)
    bot_token = os.environ.get("TELEGRAM_BOT")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT environment variable not set. Please configure it on Railway.app.")
    
    application = Application.builder().token(bot_token).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("generate", generate_command))

    # Run the bot until the user presses Ctrl-C or the process receives SIGINT, SIGTERM or SIGABRT
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
