import logging
import os
import random
import string
import asyncio
import warnings
import io

# Import TimedOut for FloodWait handling
from telegram.error import BadRequest, TimedOut # Added TimedOut

# Suppress the PTBUserWarning
warnings.filterwarnings(
    "ignore",
    message="If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message.",
    category=UserWarning,
    module="telegram.ext.conversationhandler"
)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
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
INITIAL_MENU, ASK_COUNT, ASK_PATTERN, BULK_LIST, HOW_TO_INFO, SET_LANGUAGE = range(6)

# --- Translations Dictionary ---
translations = {
    'en': {
        'welcome': "Welcome to RipperTek Bot. Please choose:",
        'generate_username_btn': "🔤 Generate Username",
        'bulk_check_btn': "📄 Bulk Check List",
        'how_to_btn': "❓ How To",
        'language_btn': "🌐 Language / اللغة",
        'english_btn': "English",
        'arabic_btn': "العربية",
        'language_selection': "Please choose your language:",
        'language_set': "Language set to English.",
        'how_many_names': "How many names would you like to generate and check (1-500)?",
        'invalid_number': "Please enter a number between 1 and 500.",
        'send_pattern': "Send a sample pattern (e.g., `user_x_x_x` where 'x' is replaced by random chars/digits):",
        'invalid_pattern': "Please provide a valid pattern.",
        'searching_names': "Searching for {count} usernames based on '{pattern}', please wait...",
        'large_request_warning': "⚠️ Warning: Checking a large number of names might take a long time and could sometimes lead to timeouts or forced pauses due to Telegram's rate limits.", # Updated warning
        'checked_variations': "Checked {total_checked} variations for pattern '{pattern}'.\n",
        'available_names': "✅ Available ({count}):",
        'no_available_names': "😔 No available usernames found among the generated ones.",
        'taken_names': "\n❌ Taken ({count}):",
        'all_generated_available': "\n🎉 All generated variations were found available! (Unlikely for large numbers)",
        'result_too_long': "Result too long to display fully. Showing summary:\nTotal checked: {total_checked}\n✅ Available: {available_count}\n❌ Taken: {taken_count}\n\nTry a smaller generation count for full list display, or use Bulk Check for specific lists.",
        'download_available_btn': "⬇️ Download Available Names",
        'download_all_checked_btn': "⬇️ Download All Checked Names",
        'back_btn': "⬅️ Back",
        'stop_btn': "🛑 Stop",
        'send_list_usernames': "Send a list of usernames (one per line):",
        'no_usernames_provided': "Please provide a list of usernames.",
        'checking_list': "Checking your list, please wait...",
        'checked_list_usernames': "Checked {total_checked} usernames from your list.\n",
        'none_available_in_list': "😔 None of the provided usernames are available.",
        'all_provided_available': "\n🎉 All provided usernames were found available! (Unlikely for large numbers)",
        'list_result_too_long': "Result too long to display fully. Showing summary:\nTotal checked: {total_checked}\n✅ Available: {available_count}\n❌ Taken: {taken_count}\n\nConsider smaller lists for full display.",
        'operation_cancelled': "❌ Operation cancelled. Type /start to begin again.",
        'no_names_to_save': "No names to save in {filename}.",
        'failed_to_send_file': "Failed to send the file: {error}",
        'how_to_content': (
            "**How RipperTek Bot Works:**\n\n"
            "This bot helps you find available Telegram usernames. "
            "You can either:\n\n"
            "1. **Generate Usernames:** First, tell me how many names to find, then provide a pattern like `user_x_x_x` (where 'x' is a placeholder that will be replaced by random letters/digits). The bot will generate variations and check their availability.\n\n"
            "2. **Bulk Check List:** Send a list of usernames (one per line) and the bot will check each one for availability.\n\n"
            "**Aim:** To simplify the process of finding unique and unused Telegram usernames for your channels, groups, or personal profiles.\n\n"
            "**Important Note on Accuracy:** Username availability checks are performed using Telegram's bot API (specifically, by attempting to retrieve chat information). While this method is generally accurate for public usernames, **it may not be 100% precise for all cases.** Some usernames might appear available through the bot but are actually taken by private entities or certain types of accounts, due to limitations in what bot APIs can check. **Always confirm availability directly on Telegram when attempting to set a username.**"
        ),
        'flood_wait_message': "❗️ Bot paused due to Telegram's flood control. Retrying in {retry_after} seconds. Please wait, this might take a while for large requests." # New flood wait message
    },
    'ar': {
        'welcome': "أهلاً بك في بوت RipperTek. الرجاء الاختيار:",
        'generate_username_btn': "🔤 توليد اسم مستخدم",
        'bulk_check_btn': "📄 فحص قائمة جماعية",
        'how_to_btn': "❓ كيفية الاستخدام",
        'language_btn': "🌐 اللغة / Language",
        'english_btn': "English",
        'arabic_btn': "العربية",
        'language_selection': "الرجاء اختيار لغتك:",
        'language_set': "تم تعيين اللغة إلى العربية.",
        'how_many_names': "كم عدد الأسماء التي تود توليدها وفحصها (1-500)؟",
        'invalid_number': "الرجاء إدخال رقم بين 1 و 500.",
        'send_pattern': "أرسل نمطاً مثالياً (مثل `user_x_x_x` حيث يتم استبدال 'x' بأحرف/أرقام عشوائية):",
        'invalid_pattern': "الرجاء توفير نمط صالح.",
        'searching_names': "جارٍ البحث عن {count} اسم مستخدم بناءً على '{pattern}'، الرجاء الانتظار...",
        'large_request_warning': "⚠️ تحذير: فحص عدد كبير من الأسماء قد يستغرق وقتاً طويلاً وقد يؤدي أحياناً إلى مهلة أو توقف إجباري بسبب قيود الطلبات من تلغرام.",
        'checked_variations': "تم فحص {total_checked} اختلافاً للنمط '{pattern}'.\n",
        'available_names': "✅ متاح ({count}):",
        'no_available_names': "😔 لم يتم العثور على أسماء مستخدمين متاحة ضمن الأسماء التي تم توليدها.",
        'taken_names': "\n❌ محجوز ({count}):",
        'all_generated_available': "\n🎉 جميع الاختلافات التي تم توليدها وُجدت متاحة! (غير مرجح للأعداد الكبيرة)",
        'result_too_long': "النتيجة طويلة جداً لعرضها بالكامل. عرض ملخص:\nإجمالي المفحوص: {total_checked}\n✅ متاح: {available_count}\n❌ محجوز: {taken_count}\n\nجرب عدداً أقل من التوليد لعرض القائمة بالكامل، أو استخدم الفحص الجماعي لقوائم محددة.",
        'download_available_btn': "⬇️ تحميل الأسماء المتاحة",
        'download_all_checked_btn': "⬇️ تحميل جميع الأسماء المفحوصة",
        'back_btn': "⬅️ رجوع",
        'stop_btn': "🛑 إيقاف",
        'send_list_usernames': "أرسل قائمة بأسماء المستخدمين (اسم واحد في كل سطر):",
        'no_usernames_provided': "الرجاء توفير قائمة بأسماء المستخدمين.",
        'checking_list': "جارٍ فحص قائمتك، الرجاء الانتظار...",
        'checked_list_usernames': "تم فحص {total_checked} اسم مستخدم من قائمتك.\n",
        'none_available_in_list': "😔 لا يوجد أي من أسماء المستخدمين المتوفرة في القائمة التي قدمتها.",
        'all_provided_available': "\n🎉 جميع أسماء المستخدمين المقدمة وُجدت متاحة! (غير مرجح للأعداد الكبيرة)",
        'list_result_too_long': "النتيجة طويلة جداً لعرضها بالكامل. عرض ملخص:\nإجمالي المفحوص: {total_checked}\n✅ متاح: {available_count}\n❌ محجوز: {taken_count}\n\nالرجاء النظر في قوائم أصغر للعرض الكامل.",
        'operation_cancelled': "❌ تم إلغاء العملية. اكتب /start للبدء من جديد.",
        'no_names_to_save': "لا توجد أسماء لحفظها في {filename}.",
        'failed_to_send_file': "فشل في إرسال الملف: {error}",
        'how_to_content': (
            "**كيف يعمل بوت RipperTek:**\n\n"
            "يساعدك هذا البوت في العثور على أسماء مستخدمين متاحة في تيليجرام. "
            "يمكنك إما:\n\n"
            "1. **توليد أسماء مستخدمين:** أولاً، أخبرني كم عدد الأسماء التي تريد العثور عليها، ثم قدم نمطاً مثل `user_x_x_x` (حيث يتم استبدال 'x' بأحرف/أرقام عشوائية). سيقوم البوت بتوليد اختلافات وفحص توفرها.\n\n"
            "2. **فحص قائمة جماعية:** أرسل قائمة بأسماء المستخدمين (اسم واحد في كل سطر) وسيقوم البوت بفحص كل اسم للتحقق من توفره.\n\n"
            "**الهدف:** تبسيط عملية العثور على أسماء مستخدمين فريدة وغير مستخدمة في تيليجرام لقنواتك أو مجموعاتك أو ملفاتك الشخصية.\n\n"
            "**ملاحظة هامة حول الدقة:** يتم إجراء فحوصات توفر اسم المستخدم باستخدام واجهة برمجة تطبيقات بوت تيليجرام (على وجه التحديد، عن طريق محاولة استرداد معلومات الدردشة). بينما هذه الطريقة دقيقة بشكل عام لأسماء المستخدمين العامة، **قد لا تكون دقيقة بنسبة 100% في جميع الحالات.** قد تظهر بعض أسماء المستخدمين متاحة من خلال البوت ولكنها في الواقع محجوزة بواسطة كيانات خاصة أو أنواع معينة من الحسابات، بسبب قيود في ما يمكن لواجهات برمجة تطبيقات البوت فحصه. **تأكد دائماً من التوفر مباشرة على تيليجرام عند محاولة تعيين اسم مستخدم.**"
        ),
        'flood_wait_message': "❗️ تم إيقاف البوت مؤقتاً بسبب قيود تلغرام على الطلبات. سيعاود المحاولة بعد {retry_after} ثانية. الرجاء الانتظار، قد يستغرق هذا بعض الوقت للطلبات الكبيرة."
    }
}

# --- Helper function to get translated text ---
def get_text(context: ContextTypes.DEFAULT_TYPE, key: str, **kwargs) -> str:
    lang = context.user_data.get('language', 'en')
    text = translations.get(lang, translations['en']).get(key, f"Translation missing for '{key}' in '{lang}'")
    return text.format(**kwargs)

# --- Helper Function to create Main Menu Keyboard ---
def get_main_menu_keyboard(context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(get_text(context, 'generate_username_btn'), callback_data='generate')],
        [InlineKeyboardButton(get_text(context, 'bulk_check_btn'), callback_data='bulk')],
        [InlineKeyboardButton(get_text(context, 'how_to_btn'), callback_data='how_to')],
        [InlineKeyboardButton(get_text(context, 'language_btn'), callback_data='set_language')]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Stop & Back Buttons Keyboard Helper ---
def get_stop_and_back_keyboard(context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(get_text(context, 'back_btn'), callback_data='back')],
        [InlineKeyboardButton(get_text(context, 'stop_btn'), callback_data='stop')]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Result Screen Buttons Helper ---
def get_result_screen_keyboard(context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(get_text(context, 'download_available_btn'), callback_data='download_available')],
        [InlineKeyboardButton(get_text(context, 'download_all_checked_btn'), callback_data='download_all_checked')],
        [InlineKeyboardButton(get_text(context, 'back_btn'), callback_data='back')],
        [InlineKeyboardButton(get_text(context, 'stop_btn'), callback_data='stop')]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Language Selection Keyboard ---
def get_language_keyboard():
    keyboard = [
        [InlineKeyboardButton("English", callback_data='lang_en')],
        [InlineKeyboardButton("العربية", callback_data='lang_ar')],
        [InlineKeyboardButton("⬅️ Back", callback_data='back')]
    ]
    return InlineKeyboardMarkup(keyboard)


# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'language' not in context.user_data:
        context.user_data['language'] = 'en'
    await update.message.reply_text(get_text(context, 'welcome'), reply_markup=get_main_menu_keyboard(context))
    return INITIAL_MENU

# Callback query handler (for all inline buttons)
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'generate':
        await query.edit_message_text(get_text(context, 'how_many_names'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_COUNT
    elif query.data == 'bulk':
        await query.edit_message_text(get_text(context, 'send_list_usernames'), reply_markup=get_stop_and_back_keyboard(context))
        return BULK_LIST
    elif query.data == 'how_to':
        await query.edit_message_text(
            get_text(context, 'how_to_content'),
            parse_mode='Markdown',
            reply_markup=get_stop_and_back_keyboard(context)
        )
        return HOW_TO_INFO
    elif query.data == 'set_language':
        await query.edit_message_text(get_text(context, 'language_selection'), reply_markup=get_language_keyboard())
        return SET_LANGUAGE
    elif query.data.startswith('lang_'):
        return await set_language_callback(update, context)
    elif query.data == 'download_available':
        if 'last_available_names' in context.user_data and context.user_data['last_available_names']:
            await send_names_as_file(context, query.message.chat_id, context.user_data['last_available_names'], "available_usernames.txt")
        else:
            await query.message.reply_text(get_text(context, 'no_names_to_save', filename="available_usernames.txt"))
        await query.edit_message_text(get_text(context, 'welcome'), reply_markup=get_main_menu_keyboard(context))
        return INITIAL_MENU

    elif query.data == 'download_all_checked':
        if 'last_all_checked_results' in context.user_data and context.user_data['last_all_checked_results']:
            formatted_results = []
            for item in context.user_data['last_all_checked_results']:
                # استرجاع النص من الترجمات دون الأيقونات لتنسيق الملف
                status_key = 'available_names' if item['available'] else 'taken_names'
                status_text = translations[context.user_data['language']].get(status_key, translations['en'][status_key])
                status = status_text.replace('✅ ', '').replace(' ()', '').replace('\n❌ ', '') # إزالة الأيقونات والعداد لملف النص
                formatted_results.append(f"{item['username']} ({status})")
            await send_names_as_file(context, query.message.chat_id, formatted_results, "all_checked_usernames.txt")
        else:
            await query.message.reply_text(get_text(context, 'no_names_to_save', filename="all_checked_usernames.txt"))
        await query.edit_message_text(get_text(context, 'welcome'), reply_markup=get_main_menu_keyboard(context))
        return INITIAL_MENU

    elif query.data == 'back' or query.data == 'stop':
        await query.edit_message_text(
            get_text(context, 'welcome'),
            reply_markup=get_main_menu_keyboard(context)
        )
        return INITIAL_MENU

    return ConversationHandler.END

# Handler for language selection callback
async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang_code = query.data.split('_')[1]
    context.user_data['language'] = lang_code
    
    await query.edit_message_text(get_text(context, 'language_set'), reply_markup=get_main_menu_keyboard(context))
    return INITIAL_MENU


# Handler for count input
async def handle_count_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text.strip())
        if not (1 <= count <= 500): # Increased limit to 500
            await update.message.reply_text(get_text(context, 'invalid_number'), reply_markup=get_stop_and_back_keyboard(context))
            return ASK_COUNT
        
        context.user_data['num_to_generate_display'] = count
        await update.message.reply_text(get_text(context, 'send_pattern'), parse_mode='Markdown', reply_markup=get_stop_and_back_keyboard(context))
        return ASK_PATTERN
    except ValueError:
        await update.message.reply_text(get_text(context, 'invalid_number'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_COUNT


# Username generator logic
def generate_usernames(pattern: str, num_variations_to_try: int = 200) -> list[str]:
    letters = string.ascii_lowercase + string.digits
    generated = set()
    attempts = 0
    max_attempts = num_variations_to_try * 5
    
    PLACEHOLDER_CHAR = 'x'

    while len(generated) < num_variations_to_try and attempts < max_attempts:
        uname_chars = list(pattern)
        
        # Ensure first character is not a digit if it's a placeholder AND at the beginning
        if uname_chars and uname_chars[0] == PLACEHOLDER_CHAR:
            uname_chars[0] = random.choice(string.ascii_lowercase) # Only letters for the first char
        
        # Replace other placeholders
        for i in range(len(uname_chars)):
            if uname_chars[i] == PLACEHOLDER_CHAR and i != 0:
                uname_chars[i] = random.choice(letters)

        final_uname = "".join(uname_chars)

        if 5 <= len(final_uname) <= 32 and final_uname[0] != '_' and final_uname.replace('_', '').isalnum():
            generated.add(final_uname)
        attempts += 1
    
    return [name for name in list(generated) if 5 <= len(name) <= 32 and name[0] != '_' and name.replace('_', '').isalnum()]


# Telegram API username availability checker
async def check_username_availability(context: ContextTypes.DEFAULT_TYPE, username: str) -> tuple[bool, str, str | None]:
    if not (5 <= len(username) <= 32 and username[0] != '_' and username.replace('_', '').isalnum()):
        logger.warning(f"Invalid username format or length (pre-API check): {username}")
        return False, username, None

    try:
        chat = await context.bot.get_chat(f"@{username}")
        
        if chat.username and chat.username.lower() == username.lower():
            logger.info(f"Username @{username} already exists (get_chat successful). Chat ID: {chat.id}")
            return False, username, f"https://t.me/{chat.username}"
        
        return False, username, None
    except TimedOut as e: # Catch FloodWait
        retry_after = e.retry_after
        logger.warning(f"FLOODWAIT: Hit flood control for @{username}. Retrying in {retry_after} seconds.")
        # Send a message to the user about the pause
        await context.bot.send_message(
            chat_id=context._chat_id, # Access chat_id from context
            text=get_text(context, 'flood_wait_message', retry_after=retry_after)
        )
        await asyncio.sleep(retry_after)
        # Recursively call itself to retry the check after the sleep
        return await check_username_availability(context, username)
    except BadRequest as e:
        error_message = str(e).lower()
        if "username not found" in error_message or "chat not found" in error_message:
            logger.info(f"Username @{username} is likely available (BadRequest: {error_message}).")
            return True, username, f"https://t.me/{username}"
        logger.error(f"Telegram API BadRequest checking username {username}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking username {username}: {e}")

    return False, username, None

# Handle generated pattern request
async def ask_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = update.message.text.strip().lower()
    if not pattern:
        await update.message.reply_text(get_text(context, 'invalid_pattern'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_PATTERN

    num_to_display = context.user_data.get('num_to_generate_display', 20)
    num_variations_to_try = num_to_display 

    warning_text = ""
    if num_to_display > 100: # Warning for numbers over 100
        warning_text = get_text(context, 'large_request_warning') + "\n\n"

    await update.message.reply_text(warning_text + get_text(context, 'searching_names', count=num_to_display, pattern=pattern), parse_mode='Markdown', reply_markup=get_stop_and_back_keyboard(context))
    
    raw_usernames = generate_usernames(pattern, num_variations_to_try)
    logger.info(f"DEBUG_GENERATE: Pattern: '{pattern}', Generated {len(raw_usernames)} raw names. First 10: {raw_usernames[:10]}")
    
    all_results = []
    
    for uname in raw_usernames:
        is_available, username_str, link = await check_username_availability(context, uname)
        all_results.append({'username': username_str, 'available': is_available, 'link': link})
        await asyncio.sleep(0.05)

    available_names_info = [r for r in all_results if r['available']]
    taken_names_info = [r for r in all_results if not r['available']]

    context.user_data['last_available_names'] = [r['username'] for r in available_names_info]
    context.user_data['last_all_checked_results'] = all_results

    text_parts = [get_text(context, 'checked_variations', total_checked=len(all_results), pattern=pattern)]

    def format_names_for_display(name_objects: list[dict]) -> list[str]:
        formatted = []
        for item in name_objects:
            if item['link']:
                formatted.append(f"[`@{item['username']}`]({item['link']})") # Clickable link
            else:
                formatted.append(f"`@{item['username']}`") # Just inline code
        return formatted

    if available_names_info:
        text_parts.append(get_text(context, 'available_names', count=len(available_names_info)))
        display_available = format_names_for_display(available_names_info[:num_to_display])
        text_parts.append("\n".join(display_available))
        if len(available_names_info) > num_to_display:
            text_parts.append(f"...and {len(available_names_info) - num_to_display} more available names.")
    else:
        text_parts.append(get_text(context, 'no_available_names'))

    if taken_names_info:
        MAX_TAKEN_TO_DISPLAY = 20
        text_parts.append(get_text(context, 'taken_names', count=len(taken_names_info)))
        display_taken = format_names_for_display(taken_names_info[:MAX_TAKEN_TO_DISPLAY])
        text_parts.append("\n".join(display_taken))
        if len(taken_names_info) > MAX_TAKEN_TO_DISPLAY:
            text_parts.append(f"...and {len(taken_names_info) - MAX_TAKEN_TO_DISPLAY} more taken names.")
    else:
        text_parts.append(get_text(context, 'all_generated_available'))


    final_text = "\n".join(text_parts)
    
    if len(final_text) > 4000:
        final_text = get_text(context, 'result_too_long', total_checked=len(all_results), available_count=len(available_names_info), taken_count=len(taken_names_info))

    await update.message.reply_text(final_text, parse_mode='Markdown', reply_markup=get_result_screen_keyboard(context))
    return INITIAL_MENU

# Handle bulk checking request
async def bulk_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [n.strip() for n in update.message.text.splitlines() if n.strip()]
    if not names:
        await update.message.reply_text(get_text(context, 'no_usernames_provided'), reply_markup=get_stop_and_back_keyboard(context))
        return BULK_LIST

    warning_text = ""
    if len(names) > 100: # Warning for numbers over 100 in bulk check
        warning_text = get_text(context, 'large_request_warning') + "\n\n"

    await update.message.reply_text(warning_text + get_text(context, 'checking_list'), parse_mode='Markdown', reply_markup=get_stop_and_back_keyboard(context))

    all_results = []
    for name in names:
        is_available, username_str, link = await check_username_availability(context, name)
        all_results.append({'username': username_str, 'available': is_available, 'link': link})
        await asyncio.sleep(0.05)

    available_names_info = [r for r in all_results if r['available']]
    taken_names_info = [r for r in all_results if not r['available']]

    context.user_data['last_available_names'] = [r['username'] for r in available_names_info]
    context.user_data['last_all_checked_results'] = all_results

    text_parts = [get_text(context, 'checked_list_usernames', total_checked=len(all_results))]

    def format_names_for_display(name_objects: list[dict]) -> list[str]:
        formatted = []
        for item in name_objects:
            if item['link']:
                formatted.append(f"[`@{item['username']}`]({item['link']})")
            else:
                formatted.append(f"`@{item['username']}`")
        return formatted

    if available_names_info:
        text_parts.append(get_text(context, 'available_names', count=len(available_names_info)))
        text_parts.append("\n".join(format_names_for_display(available_names_info)))
    else:
        text_parts.append(get_text(context, 'none_available_in_list'))

    if taken_names_info:
        MAX_TAKEN_TO_DISPLAY = 20
        text_parts.append(get_text(context, 'taken_names', count=len(taken_names_info)))
        display_taken = format_names_for_display(taken_names_info[:MAX_TAKEN_TO_DISPLAY])
        text_parts.append("\n".join(display_taken))
        if len(taken_names_info) > MAX_TAKEN_TO_DISPLAY:
            text_parts.append(f"...and {len(taken_names_info) - MAX_TAKEN_TO_DISPLAY} more taken names.")
    else:
        text_parts.append(get_text(context, 'all_provided_available'))

    final_text = "\n".join(text_parts)
    
    if len(final_text) > 4000:
        final_text = get_text(context, 'list_result_too_long', total_checked=len(all_results), available_count=len(available_names_info), taken_count=len(taken_names_info))

    await update.message.reply_text(final_text, parse_mode='Markdown', reply_markup=get_result_screen_keyboard(context))
    return INITIAL_MENU

# Cancel command handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_text(context, 'operation_cancelled'), reply_markup=get_main_menu_keyboard(context))
    return ConversationHandler.END

# Helper function to send a list of names as a text file
async def send_names_as_file(context: ContextTypes.DEFAULT_TYPE, chat_id: int, names_list: list[str], filename: str):
    if not names_list:
        await context.bot.send_message(chat_id=chat_id, text=get_text(context, 'no_names_to_save', filename=filename))
        return

    file_content = "\n".join(names_list)
    file_stream = io.BytesIO(file_content.encode('utf-8'))
    file_stream.name = filename

    try:
        await context.bot.send_document(chat_id=chat_id, document=InputFile(file_stream))
        logger.info(f"Sent {filename} to chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send document {filename} to chat {chat_id}: {e}")
        await context.bot.send_message(chat_id=chat_id, text=get_text(context, 'failed_to_send_file', error=str(e)))


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
            ],
            SET_LANGUAGE: [
                CallbackQueryHandler(button, pattern="^lang_en$|^lang_ar$|^back$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(button, pattern="^back$|^stop$|^download_available$|^download_all_checked$")
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
