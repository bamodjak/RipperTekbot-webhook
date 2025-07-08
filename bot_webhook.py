import logging
import os
import random
import string
import asyncio
import warnings
import io
import re

# Suppress the PTBUserWarning
warnings.filterwarnings(
    "ignore",
    message="If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message.",
    category=UserWarning,
    module="telegram.ext.conversationhandler"
)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import BadRequest, TimedOut
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
INITIAL_MENU, ASK_COUNT, ASK_PATTERN, ASK_DELAY, BULK_LIST, HOW_TO_INFO, SET_LANGUAGE = range(7)

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
        'send_pattern': "Send a sample pattern (e.g., `user_x_x_x` where 'x' is replaced by random chars/digits). Use double quotes `\"\"` for fixed parts (e.g., `\"my_name\"_x`):",
        'invalid_pattern': "Please provide a valid pattern.",
        'ask_delay': "Enter a delay between checks in seconds (e.g., 0.1 for 100ms, 1 for 1s). Enter 0 for no additional delay:",
        'invalid_delay': "Please enter a valid number for delay (e.g., 0.1, 1, 5).",
        'searching_names': "Searching for {count} usernames based on '{pattern}', please wait...",
        'checking_progress': "Checking... {current_checked} of {total_to_check} names processed.\n✅ Available: {available_count}\n❌ Taken: {taken_count}\n\n(Updates may be delayed due to Telegram's limits)", # Updated progress message
        'large_request_warning': "⚠️ Warning: Checking a large number of names might take a long time and could sometimes lead to timeouts or forced pauses due to Telegram's rate limits.",
        'checked_variations': "Checked {total_checked} variations for pattern '{pattern}'.\n",
        'available_names': "✅ Available ({count}):",
        'no_available_names': "😔 No available usernames found among the generated ones.",
        'taken_names': "\n❌ Taken ({count}):",
        'all_generated_available': "\n🎉 All generated variations were found available! (Unlikely for large numbers)",
        'result_too_long': "Result too long to display fully. Showing summary:\nTotal checked: {total_checked}\n✅ Available: {available_count}\n❌ Taken: {taken_count}\n\nTry a smaller generation count for full list display, or use Bulk Check for specific lists.",
        'download_available_btn': "⬇️ Download Available Names",
        'download_all_checked_btn': "⬇️ Download All Checked Names",
        'back_btn': "⬅️ Back",
        'stop_btn': "🛑 Stop and Show Results",
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
            "1. **Generate Usernames:** First, tell me how many names to find, then provide a pattern like `user_x_x_x` (where 'x' is a placeholder that will be replaced by random letters/digits). Use double quotes `\"\"` for fixed parts (e.g., `\"my_name\"_x` will keep \"my_name\" as is). The bot will generate variations and check their availability.\n\n"
            "2. **Bulk Check List:** Send a list of usernames (one per line) and the bot will check each one for availability.\n\n"
            "**Aim:** To simplify the process of finding unique and unused Telegram usernames for your channels, groups, or personal profiles.\n\n"
            "**Important Note on Accuracy:** Username availability checks are performed using Telegram's bot API (specifically, by attempting to retrieve chat information). While this method is generally accurate for public usernames, **it may not be 100% precise for all cases.** Some usernames might appear available through the bot but are actually taken by private entities or certain types of accounts, due to limitations in what bot APIs can check. **Always confirm availability directly on Telegram when attempting to set a username.**"
        ),
        'flood_wait_message': "❗️ Bot paused due to Telegram's flood control. Retrying in {retry_after} seconds. Please wait, this might take a while for large requests."
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
        'send_pattern': "أرسل نمطاً مثالياً (مثل `user_x_x_x` حيث يتم استبدال 'x' بأحرف/أرقام عشوائية). استخدم علامتي الاقتباس `\"\"` للأجزاء الثابتة (مثال: `\"my_name\"_x` سيبقي \"my_name\" كما هي):",
        'invalid_pattern': "الرجاء توفير نمط صالح.",
        'ask_delay': "أدخل تأخيراً بين عمليات الفحص بالثواني (مثال: 0.1 لـ 100 مللي ثانية، 1 لـ 1 ثانية). أدخل 0 لعدم وجود تأخير إضافي:",
        'invalid_delay': "الرجاء إدخال رقم صالح للتأخير (مثال: 0.1, 1, 5).",
        'searching_names': "جارٍ البحث عن {count} اسم مستخدم بناءً على '{pattern}'، الرجاء الانتظار...",
        'checking_progress': "جارٍ الفحص... {current_checked} من {total_to_check} اسم تمت معالجته.\n✅ متاح: {available_count}\n❌ محجوز: {taken_count}\n\n(قد تتأخر التحديثات بسبب قيود تلغرام)", # Updated progress message
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
        'stop_btn': "🛑 إيقاف وعرض النتائج",
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
            "1. **توليد أسماء مستخدمين:** أولاً، أخبرني كم عدد الأسماء التي تريد العثور عليها، ثم قدم نمطاً مثل `user_x_x_x` (حيث يتم استبدال 'x' بأحرف/أرقام عشوائية). استخدم علامتي الاقتباس `\"\"` للأجزاء الثابتة (مثال: `\"my_name\"_x` سيبقي \"my_name\" كما هي). سيقوم البوت بتوليد اختلافات وفحص توفرها.\n\n"
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
        [InlineKeyboardButton(get_text(context, 'stop_btn'), callback_data='stop_processing')]
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
    context.user_data['stop_requested'] = False
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
                status_key = 'available_names' if item['available'] else 'taken_names'
                status_text = translations[context.user_data['language']].get(status_key, translations['en'][status_key])
                status = status_text.replace('✅ ', '').replace(' ()', '').replace('\n❌ ', '')
                formatted_results.append(f"{item['username']} ({status})")
            await send_names_as_file(context, query.message.chat_id, formatted_results, "all_checked_usernames.txt")
        else:
            await query.message.reply_text(get_text(context, 'no_names_to_save', filename="all_checked_usernames.txt"))
        await query.edit_message_text(get_text(context, 'welcome'), reply_markup=get_main_menu_keyboard(context))
        return INITIAL_MENU

    elif query.data == 'back':
        context.user_data['stop_requested'] = True
        await query.edit_message_text(
            get_text(context, 'welcome'),
            reply_markup=get_main_menu_keyboard(context)
        )
        return INITIAL_MENU
    
    elif query.data == 'stop_processing':
        context.user_data['stop_requested'] = True
        await query.edit_message_text(get_text(context, 'operation_cancelled'), reply_markup=get_main_menu_keyboard(context))
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
        if not (1 <= count <= 500):
            await update.message.reply_text(get_text(context, 'invalid_number'), reply_markup=get_stop_and_back_keyboard(context))
            return ASK_COUNT
        
        context.user_data['num_to_generate_display'] = count
        await update.message.reply_text(get_text(context, 'send_pattern'), parse_mode='Markdown', reply_markup=get_stop_and_back_keyboard(context))
        return ASK_PATTERN
    except ValueError:
        await update.message.reply_text(get_text(context, 'invalid_number'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_COUNT

# Handler for pattern input
async def handle_pattern_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = update.message.text.strip()
    if not pattern:
        await update.message.reply_text(get_text(context, 'invalid_pattern'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_PATTERN
    
    context.user_data['pattern'] = pattern
    await update.message.reply_text(get_text(context, 'ask_delay'), reply_markup=get_stop_and_back_keyboard(context))
    return ASK_DELAY

# Handler for delay input (This handler now directly initiates the main processing loop)
async def handle_delay_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        delay = float(update.message.text.strip())
        if delay < 0:
            raise ValueError
        context.user_data['check_delay'] = delay
        
        # --- Start of the main processing logic (moved from ask_pattern) ---
        pattern = context.user_data['pattern']
        num_to_display = context.user_data.get('num_to_generate_display', 20)
        check_delay = context.user_data.get('check_delay', 0.05)

        warning_text = ""
        if num_to_display > 100:
            warning_text = get_text(context, 'large_request_warning') + "\n\n"

        initial_message = await update.message.reply_text(warning_text + get_text(context, 'searching_names', count=num_to_display, pattern=pattern), parse_mode='Markdown', reply_markup=get_stop_and_back_keyboard(context))
        context.user_data['progress_message_id'] = initial_message.message_id
        context.user_data['stop_requested'] = False

        raw_usernames = generate_usernames(pattern, num_to_display)
        logger.info(f"DEBUG_GENERATE: Pattern: '{pattern}', Generated {len(raw_usernames)} raw names. First 10: {raw_usernames[:10]}")
        
        all_results = []
        available_count = 0
        taken_count = 0
        last_update_time = asyncio.get_event_loop().time()
        
        # Updated: Attempt to update frequently
        UPDATE_INTERVAL_SECONDS = 1 
        UPDATE_INTERVAL_COUNT = 1 

        for i, uname in enumerate(raw_usernames):
            if context.user_data.get('stop_requested'):
                logger.info("Stop requested by user. Breaking loop.")
                break

            is_available, username_str, link = await check_username_availability(context, uname)
            all_results.append({'username': username_str, 'available': is_available, 'link': link})
            if is_available:
                available_count += 1
            else:
                taken_count += 1

            current_time = asyncio.get_event_loop().time()
            if (i + 1) % UPDATE_INTERVAL_COUNT == 0 or (current_time - last_update_time) >= UPDATE_INTERVAL_SECONDS:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=context.user_data['progress_message_id'],
                        text=warning_text + get_text(context, 'checking_progress', 
                                                    current_checked=i+1, 
                                                    total_to_check=len(raw_usernames),
                                                    available_count=available_count,
                                                    taken_count=taken_count),
                        parse_mode='Markdown',
                        reply_markup=get_stop_and_back_keyboard(context)
                    )
                    last_update_time = current_time
                except BadRequest as e: # Catch BadRequest specific to editMessageText rate limits
                    logger.warning(f"Failed to edit progress message (likely rate limit or formatting): {e}. Will try again later.")
                except Exception as e:
                    logger.error(f"Unexpected error when editing progress message: {e}. Chat ID: {update.effective_chat.id}, Message ID: {context.user_data['progress_message_id']}")
                
            await asyncio.sleep(check_delay)

        await display_results(update, context, all_results, is_final=True, pattern=pattern)
        return INITIAL_MENU
        # --- End of main processing logic ---

    except ValueError:
        await update.message.reply_text(get_text(context, 'invalid_delay'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_DELAY

# This function is now just a helper to display final/partial results
# The main processing loop moved to handle_delay_input for pattern generation and bulk_list
async def display_results(update: Update, context: ContextTypes.DEFAULT_TYPE, all_results: list[dict], is_final: bool, pattern: str = None):
    available_names_info = [r for r in all_results if r['available']]
    taken_names_info = [r for r in all_results if not r['available']]

    context.user_data['last_available_names'] = [r['username'] for r in available_names_info]
    context.user_data['last_all_checked_results'] = all_results

    text_parts = []
    if pattern:
        text_parts.append(get_text(context, 'checked_variations', total_checked=len(all_results), pattern=pattern))
    else: # For bulk list
        text_parts.append(get_text(context, 'checked_list_usernames', total_checked=len(all_results)))


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
        display_available = format_names_for_display(available_names_info)
        text_parts.append("\n".join(display_available))
        if len(available_names_info) > context.user_data.get('num_to_generate_display', len(available_names_info)):
            text_parts.append(f"...and {len(available_names_info) - context.user_data.get('num_to_generate_display', len(available_names_info))} more available names.")
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

    # This should always be a NEW message when results are displayed (final or partial on stop)
    await update.effective_chat.send_message(final_text, parse_mode='Markdown', reply_markup=get_result_screen_keyboard(context))


# This function is now ONLY for handling pattern input and moving to ASK_DELAY.
# The main processing logic is moved to handle_delay_input.
# It's called when the user sends a pattern.
async def ask_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This function's content has been moved to handle_pattern_input.
    # It just returns the state for the conversation handler.
    pass # This function should ideally not be called directly from ConversationHandler anymore
    # Its logic is now in handle_pattern_input, which is the MessageHandler for ASK_PATTERN state.


# Handle bulk checking request (modified to match new processing flow)
async def bulk_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [n.strip() for n in update.message.text.splitlines() if n.strip()]
    if not names:
        await update.message.reply_text(get_text(context, 'no_usernames_provided'), reply_markup=get_stop_and_back_keyboard(context))
        return BULK_LIST

    warning_text = ""
    if len(names) > 100:
        warning_text = get_text(context, 'large_request_warning') + "\n\n"

    context.user_data['check_delay'] = 0.05 # Default delay for bulk check

    initial_message = await update.message.reply_text(warning_text + get_text(context, 'checking_list'), parse_mode='Markdown', reply_markup=get_stop_and_back_keyboard(context))
    context.user_data['progress_message_id'] = initial_message.message_id
    context.user_data['stop_requested'] = False

    all_results = []
    available_count = 0
    taken_count = 0
    last_update_time = asyncio.get_event_loop().time()
    
    UPDATE_INTERVAL_SECONDS = 1
    UPDATE_INTERVAL_COUNT = 1

    for i, name in enumerate(names):
        if context.user_data.get('stop_requested'):
            logger.info("Stop requested by user. Breaking loop.")
            break

        is_available, username_str, link = await check_username_availability(context, name)
        all_results.append({'username': username_str, 'available': is_available, 'link': link})
        if is_available:
            available_count += 1
        else:
            taken_count += 1

        current_time = asyncio.get_event_loop().time()
        if (i + 1) % UPDATE_INTERVAL_COUNT == 0 or (current_time - last_update_time) >= UPDATE_INTERVAL_SECONDS:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data['progress_message_id'],
                    text=warning_text + get_text(context, 'checking_progress', 
                                                current_checked=i+1, 
                                                total_to_check=len(names),
                                                available_count=available_count,
                                                taken_count=taken_count),
                    parse_mode='Markdown',
                    reply_markup=get_stop_and_back_keyboard(context)
                )
                last_update_time = current_time
            except BadRequest as e:
                logger.warning(f"Failed to edit progress message (likely rate limit or formatting): {e}. Chat ID: {update.effective_chat.id}, Message ID: {context.user_data['progress_message_id']}")
            except Exception as e:
                logger.error(f"Unexpected error when editing progress message: {e}. Chat ID: {update.effective_chat.id}, Message ID: {context.user_data['progress_message_id']}")

        await asyncio.sleep(context.user_data['check_delay'])

    await display_results(update, context, all_results, is_final=True)
    return INITIAL_MENU

# Cancel command handler (for general cancellation, not specific stop during process)
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['stop_requested'] = True
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
                CallbackQueryHandler(button, pattern="^back$|^stop_processing$")
            ],

            ASK_PATTERN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pattern_input), # Renamed ask_pattern to handle_pattern_input
                CallbackQueryHandler(button, pattern="^back$|^stop_processing$")
            ],
            
            ASK_DELAY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delay_input), # This now starts processing
                CallbackQueryHandler(button, pattern="^back$|^stop_processing$")
            ],

            BULK_LIST: [ # This state directly handles bulk list input and starts processing
                MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_list),
                CallbackQueryHandler(button, pattern="^back$|^stop_processing$")
            ],
            HOW_TO_INFO: [
                CallbackQueryHandler(button, pattern="^back$|^stop_processing$")
            ],
            SET_LANGUAGE: [
                CallbackQueryHandler(button, pattern="^lang_en$|^lang_ar$|^back$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(button, pattern="^back$|^stop_processing$|^download_available$|^download_all_checked$|^stop$")
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
