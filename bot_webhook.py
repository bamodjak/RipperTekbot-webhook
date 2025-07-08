import logging
import os
import random
import string
import asyncio
import warnings
import io
import re
import httpx
from typing import List, Dict, Set

# Import get_english_words_set from the first code's dependencies
try:
    from english_words import get_english_words_set
    # Load English words
    ENGLISH_WORDS = get_english_words_set(['web2'], lower=True)
except ImportError:
    logging.warning("english_words library not found. English word generation will be limited or not function as expected.")
    ENGLISH_WORDS = set() # Fallback empty set if library not present

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import BadRequest, TimedOut, RetryAfter
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Suppress the PTBUserWarning
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
    raise RuntimeError("TELEGRAM_TOKEN environment variable not set!")

# --- States for ConversationHandler (Merged from both codes) ---
INITIAL_MENU, \
ASK_USERNAME_COUNT, ASK_PATTERN, ASK_DELAY, BULK_LIST, \
HOW_TO_INFO, SET_LANGUAGE, \
ASK_WORD_LENGTH, ASK_WORD_FORMULA, ASK_WORD_COUNT, SHOW_WORD_RESULTS = range(11)


# --- Data for Word Generation ---
# Arabic words dataset (ensuring correct UTF-8 representation)
ARABIC_WORDS = {
    'كتاب', 'مدرسة', 'بيت', 'قلم', 'ورقة', 'طالب', 'معلم', 'درس', 'امتحان', 'نجاح',
    'حب', 'سلام', 'أمل', 'نور', 'حياة', 'عمل', 'وقت', 'يوم', 'ليلة', 'صباح',
    'مساء', 'شمس', 'قمر', 'نجم', 'بحر', 'جبل', 'شجرة', 'زهرة', 'طائر', 'سمك',
    'طعام', 'ماء', 'خبز', 'لحم', 'فاكهة', 'خضار', 'لبن', 'شاي', 'قهوة', 'عصير',
    'أب', 'أم', 'ابن', 'ابنة', 'أخ', 'أخت', 'جد', 'جدة', 'عم', 'خال',
    'صديق', 'جار', 'ضيف', 'طبيب', 'مهندس', 'معلم', 'طالب', 'عامل', 'تاجر', 'فلاح',
    'سيارة', 'حافلة', 'قطار', 'طائرة', 'باب', 'نافذة', 'مفتاح', 'كرسي', 'طاولة', 'سرير',
    'لعبة', 'كرة', 'فيلم', 'كتاب', 'مجلة', 'جريدة', 'تلفاز', 'راديو', 'هاتف', 'حاسوب',
    'مال', 'ذهب', 'فضة', 'حديد', 'خشب', 'زجاج', 'بلاستيك', 'حجر', 'رمل', 'تراب',
    'نار', 'هواء', 'ريح', 'مطر', 'ثلج', 'سحاب', 'رعد', 'برق', 'قوس', 'لون',
    'أحمر', 'أزرق', 'أخضر', 'أصفر', 'أسود', 'أبيض', 'بني', 'رمادي', 'برتقالي', 'بنفسجي',
    'كبير', 'صغير', 'طويل', 'قصير', 'عريض', 'ضيق', 'سميك', 'رقيق', 'قوي', 'ضعيف',
    'سريع', 'بطيء', 'جديد', 'قديم', 'حار', 'بارد', 'جاف', 'رطب', 'نظيف', 'قذر',
    'جميل', 'قبيح', 'سهل', 'صعب', 'غني', 'فقير', 'سعيد', 'حزين', 'هادئ', 'صاخب',
    'مدينة', 'قرية', 'شارع', 'بناية', 'دكان', 'سوق', 'مسجد', 'كنيسة', 'مستشفى', 'جامعة',
    'حديقة', 'حقل', 'غابة', 'صحراء', 'وادي', 'هضبة', 'جزيرة', 'شاطئ', 'ميناء', 'قناة',
    'رقم', 'حرف', 'كلمة', 'جملة', 'صفحة', 'فصل', 'قصة', 'شعر', 'أغنية', 'رقص',
    'لحن', 'آلة', 'موسيقى', 'رسم', 'صورة', 'فن', 'ثقافة', 'تاريخ', 'جغرافيا', 'علم',
    'حق', 'عدل', 'قانون', 'حكم', 'دولة', 'حكومة', 'رئيس', 'وزير', 'موظف', 'مكتب',
    'مشروع', 'خطة', 'هدف', 'نتيجة', 'سبب', 'طريقة', 'وسيلة', 'أداة', 'آلة', 'جهاز',
    'رسالة', 'بريد', 'عنوان', 'اسم', 'لقب', 'عائلة', 'قوم', 'شعب', 'أمة', 'وطن',
    'حرب', 'سلم', 'صلح', 'اتفاق', 'معاهدة', 'قرار', 'اختيار', 'انتخاب', 'تصويت', 'رأي',
    'فكر', 'عقل', 'ذهن', 'ذكر', 'ذاكرة', 'خيال', 'حلم', 'أمنية', 'رغبة', 'حاجة',
    'خوف', 'شجاعة', 'حماس', 'حماية', 'أمان', 'خطر', 'مخاطرة', 'محاولة', 'جهد', 'عمل',
    'راحة', 'تعب', 'نوم', 'يقظة', 'استيقاظ', 'حركة', 'سكون', 'وقوف', 'جلوس', 'مشي',
    'جري', 'قفز', 'سباحة', 'طيران', 'سفر', 'رحلة', 'زيارة', 'لقاء', 'اجتماع', 'حفلة',
    'حقيقة', 'كذب', 'صدق', 'أمانة', 'خيانة', 'وفاء', 'غدر', 'مساعدة', 'خدمة', 'معروف',
    'شكر', 'امتنان', 'تقدير', 'احترام', 'تكريم', 'تهنئة', 'مباركة', 'دعاء', 'صلاة', 'عبادة',
    'إيمان', 'دين', 'عقيدة', 'قيمة', 'أخلاق', 'سلوك', 'طبع', 'خلق', 'صفة', 'ميزة',
    'خاصية', 'صفة', 'طبيعة', 'طبع', 'عادة', 'تقليد', 'عرف', 'قاعدة', 'مبدأ', 'أساس',
    'مسألة', 'موضوع', 'قضية', 'مشكلة', 'حل', 'جواب', 'سؤال', 'استفسار', 'طلب', 'رجاء',
    'أمر', 'نهي', 'إذن', 'منع', 'سماح', 'موافقة', 'رفض', 'اعتراض', 'احتجاج', 'شكوى',
    'تظلم', 'طعن', 'استئناف', 'حكم', 'قضاء', 'محكمة', 'قاضي', 'محام', 'شاهد', 'دليل',
    'برهان', 'إثبات', 'نفي', 'إقرار', 'اعتراف', 'إنكار', 'تصديق', 'تكذيب', 'تأكيد', 'نفي',
    'موافقة', 'رضا', 'قبول', 'استحسان', 'إعجاب', 'حب', 'عشق', 'هوى', 'شوق', 'حنين',
    'فراق', 'وداع', 'لقاء', 'اجتماع', 'جمع', 'تجمع', 'حشد', 'تظاهر', 'احتفال', 'عيد',
    'مناسبة', 'حدث', 'واقعة', 'حادثة', 'أمر', 'خبر', 'معلومة', 'بيان', 'إعلان', 'نشر',
    'إذاعة', 'تلفاز', 'صحافة', 'إعلام', 'وسائل', 'اتصال', 'تواصل', 'حديث', 'كلام', 'نقاش',
    'جدال', 'مناقشة', 'حوار', 'مفاوضة', 'تفاوض', 'اتفاق', 'عقد', 'صفقة', 'تجارة', 'بيع',
    'شراء', 'تسوق', 'سوق', 'دكان', 'محل', 'متجر', 'مخزن', 'مستودع', 'مصنع', 'شركة',
    'مؤسسة', 'منظمة', 'جمعية', 'نادي', 'مركز', 'معهد', 'أكاديمية', 'جامعة', 'كلية', 'مدرسة',
    'فصل', 'قسم', 'شعبة', 'وحدة', 'مجموعة', 'فريق', 'طاقم', 'عضو', 'رئيس', 'مدير',
    'موظف', 'عامل', 'خادم', 'أجير', 'مستخدم', 'صاحب', 'مالك', 'رب', 'سيد', 'قائد',
    'زعيم', 'رئيس', 'حاكم', 'ملك', 'أمير', 'سلطان', 'خليفة', 'إمام', 'شيخ', 'أستاذ',
    'دكتور', 'مهندس', 'محام', 'طبيب', 'صيدلي', 'ممرض', 'مريض', 'علاج', 'دواء', 'شفاء',
    'مرض', 'ألم', 'وجع', 'صداع', 'حمى', 'برد', 'سعال', 'عطس', 'تعب', 'إرهاق',
    'راحة', 'استرخاء', 'نوم', 'حلم', 'كابوس', 'يقظة', 'انتباه', 'تركيز', 'اهتمام', 'عناية',
    'رعاية', 'حماية', 'دفاع', 'مقاومة', 'صمود', 'تحمل', 'صبر', 'انتظار', 'ترقب', 'أمل',
    'رجاء', 'دعاء', 'تمني', 'حلم', 'طموح', 'هدف', 'غاية', 'مقصد', 'هدف', 'مرمى',
    'نتيجة', 'ثمرة', 'عاقبة', 'جزاء', 'مكافأة', 'عقاب', 'عقوبة', 'جزاء', 'مصير', 'قدر',
    'حظ', 'نصيب', 'حصة', 'قسم', 'جزء', 'بعض', 'كل', 'جميع', 'عامة', 'خاصة',
    'مشتركة', 'منفردة', 'وحيدة', 'فردية', 'جماعية', 'عمومية', 'خصوصية', 'سرية', 'علنية', 'واضحة',
    'ظاهرة', 'خفية', 'باطنة', 'داخلية', 'خارجية', 'سطحية', 'عميقة', 'بعيدة', 'قريبة', 'متوسطة'
}


# --- Constants for thresholds ---
UPDATE_INTERVAL_SECONDS = 1
UPDATE_INTERVAL_COUNT = 1
MIN_USERNAME_LENGTH = 5
MAX_USERNAME_LENGTH = 32
PLACEHOLDER_CHAR = 'x' # This is specific to username pattern generation

# Fallback words for Username generation
FALLBACK_WORDS_EN = [
    "user", "admin", "tech", "pro", "game", "bot", "tool", "alpha", "beta",
    "master", "geek", "coder", "dev", "creator", "digital", "online", "system",
    "prime", "expert", "fusion", "galaxy", "infinity", "legend", "nova", "omega",
    "phantom", "quest", "rocket", "spirit", "ultra", "vision", "wizard", "zenith",
    "swift", "spark", "glitch", "echo", "cipher", "matrix", "nexus", "orbit",
    "pulse", "quantum", "reboot", "stellar", "titan", "vortex", "zephyr", "byte",
    "liar", "love", "lion", "light", "lucky", "logic", "lunar", "limit", "level",
    "lab", "link", "leaf", "lark", "lava", "lazy", "leap", "lens", "loop", "lore",
    "blog", "chat", "club", "data", "deep", "dome", "epic", "fire", "flow", "force",
    "geek", "gold", "grid", "hero", "hive", "icon", "idea", "jolt", "jump", "king",
    "kraft", "laser", "link", "loom", "magic", "mega", "meta", "mind", "mirage", "myth",
    "nebula", "net", "night", "nova", "omega", "open", "optic", "ozone", "peak", "pixel",
    "power", "prime", "pro", "pulse", "quad", "quantum", "quest", "radar", "raid", "rank",
    "reach", "relic", "rise", "robot", "rouge", "royal", "ruby", "rush", "saber", "sage",
    "scan", "scope", "secret", "sense", "shadow", "shell", "signal", "silver", "sky", "smart",
    "solid", "soul", "space", "spark", "speed", "sphere", "spirit", "star", "steel", "storm",
    "summit", "super", "swift", "synapse", "synergy", "tact", "tag", "talk", "tech", "theta",
    "tidal", "tiger", "time", "titan", "token", "top", "track", "trail", "trap", "trend",
    "trix", "turbo", "ultra", "unity", "urban", "valor", "vanguard", "vertex", "vibe", "vision",
    "vital", "void", "volt", "vortex", "wave", "web", "wing", "wise", "wolf", "xeno",
    "yeti", "yield", "zero", "zeta", "zone", "zoom"
]

FALLBACK_WORDS_AR = [
    "مستخدم", "مسؤول", "تقنية", "محترف", "لعبة", "بوت", "أداة", "مبدع", "رقمي",
    "خبير", "عالم", "نظام", "أفق", "نجم", "بوابة", "روح", "قوة", "فارس", "بطل",
    "ذكي", "سريع", "جديد", "كبير", "قناة", "مجموعة", "مستقبل", "حياة", "علم",
    "فن", "نور", "صديق", "نصيحة", "فكرة", "سر", "حرية", "نجاح", "أمل", "طموح"
]


# --- Translations Dictionary (Merged and unified structure) ---
translations = {
    'en': {
        'welcome': "Welcome to RipperTek Bot. Please choose:",
        'generate_username_btn': "🔤 Generate Username",
        'generate_word_btn': "📚 Generate Word (EN/AR)",
        'bulk_check_btn': "📄 Bulk Check List",
        'how_to_btn': "❓ How To",
        'language_btn': "🌐 Language / اللغة",
        'english_btn': "English",
        'arabic_btn': "العربية",
        'language_selection': "Please choose your language:",
        'language_set': "Language set to English.",
        'how_many_names': "How many names would you like to generate and check (1-500)?",
        'invalid_number': "Please enter a number between 1 and 500.",
        'send_pattern': "Send a sample pattern (e.g., `user_x_x_x` where 'x' is replaced by random chars/digits). For fixed parts, enclose them in double quotes (e.g., `\"my_name\"_x`):",
        'invalid_pattern': "Please provide a valid pattern.",
        'ask_delay': "Enter a delay between checks in seconds (e.g., 0.1 for 100ms, 1 for 1s). Enter 0 for no additional delay:",
        'invalid_delay': "Please enter a valid number for delay (e.g., 0.1, 1, 5).",
        'searching_names': "Searching for {count} usernames based on '{pattern}', please wait...",
        'checking_progress': "Checking... {current_checked}/{total_to_check} processed. Remaining: {remaining_count}\n✅ Available: {available_count}\n❌ Taken: {taken_count}\n\n(Updates may be delayed due to Telegram's limits)",
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
        'flood_wait_message': "❗️ Bot paused due to Telegram's flood control. Retrying in {retry_after} seconds. الرجاء الانتظار، قد يستغرق هذا بعض الوقت للطلبات الكبيرة.",
        'stopping_process_ack': "🛑 Stopping... Results will be shown shortly.",
        'found_available_immediate': "🎉 Available now: {username}",
        'file_created': "📁 Results saved to file", # Added from first bot, and used generally

        # Word Generator Translations
        'welcome_word_gen': "🎉 Welcome to Word Generator Bot!\n\nI can generate real English or Arabic words based on your specifications:\n• Choose word length\n• Set specific letters at positions\n• Control how many words you want\n• Save results to a file\n\nChoose an option below:",
        'main_menu_word_gen': "📇 Word Generator Main Menu\n\nWhat would you like to do?",
        'generate_by_length': "📝 Generate by Length",
        'generate_by_formula': "⚙️ Generate by Formula",
        'ask_length': "Please enter the word length (number of letters):\n\nExample: 5 for 5-letter words (1-20)",
        'ask_formula': "Enter your formula pattern:\n\nFormula syntax:\n• x = any letter\n• \"text\" = fixed text (use quotes)\n• 0 = any symbol or number\n• digit = must be that digit\n\nExamples:\n• \"L\"xxx\"e\" → 5-letter words starting with L, ending with e\n• xx\"o\"x → 4-letter words with 'o' as 3rd letter\n• \"th\"xxx → 5-letter words starting with 'th'\n• xx0x → 4-letter words with symbol/number as 3rd character\n\nEnter your formula:",
        'ask_count_words': "How many words would you like? (1-500)",
        'invalid_word_length': "🚫 Please enter a valid number between 1 and 20.",
        'invalid_word_count': "🚫 Please enter a valid number between 1 and 500.",
        'invalid_formula': "🚫 Invalid formula format. Please use quotes for fixed text and x for variable letters. Example: \"L\"xxx\"e\"",
        'generating_words': "⏳ Generating words... Please wait",
        'no_words_found': "😔 No words found matching your criteria. Try different specifications.",
        'results_header': "✅ Found {count} words:\n\n",
        'download_words_btn': "💾 Download Words",
        'show_more': "📖 Show More",
        'word_file_created': "📁 Results saved to file",
        'word_error_creating_file': "❌ Error creating file"
    },
    'ar': {
        'welcome': "أهلاً بك في بوت RipperTek. الرجاء الاختيار:",
        'generate_username_btn': "🔤 توليد اسم مستخدم",
        'generate_word_btn': "📚 توليد كلمة (عربي/إنجليزي)",
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
        'checking_progress': "جارٍ الفحص... {current_checked} من {total_to_check} اسم تمت معالجته.\n✅ متاح: {available_count}\n❌ محجوز: {taken_count}\n\n(قد تتأخر التحديثات بسبب قيود تلغرام)",
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
            "**ملاحظة هامة حول الدقة:** يتم إجراء فحوصات توفر اسم المستخدم باستخدام واجهة برمجة تطبيقات بوت تيليجرام (على وجه التحديد، عن طريق محاولة استرداد معلومات الدردشة). بينما هذه الطريقة دقيقة بشكل عام لأسماء المستخدمين العامة، **قد لا تكون دقيقة بنسبة 100% في جميع الحالات.** قد تظهر بعض أسماء المستخدمين متاحة من خلال البوت ولكنها في الواقع محجوزة بواسطة كيانات خاصة أو أنواع معينة من الحسابات، بسبب قيود في ما يمكن لواجهات برمجة تطبيقات البوت فحصها. **تأكد دائماً من التوفر مباشرة على تيليجرام عند محاولة تعيين اسم مستخدم.**"
        ),
        'flood_wait_message': "❗️ Bot paused due to Telegram's flood control. Retrying in {retry_after} seconds. الرجاء الانتظار، قد يستغرق هذا بعض الوقت للطلبات الكبيرة.",
        'stopping_process_ack': "🛑 جارٍ الإيقاف... ستظهر النتائج قريباً.",
        'found_available_immediate': "🎉 متاح الآن: {username}",
        'file_created': "📁 تم حفظ النتائج في الملف", # Added from first bot, and used generally

        # Word Generator Translations
        'welcome_word_gen': "🎉 أهلاً بك في بوت مولد الكلمات!\n\nيمكنني إنشاء كلمات إنجليزية أو عربية حقيقية حسب مواصفاتك:\n• اختر طول الكلمة\n• حدد أحرف معينة في مواضع محددة\n• تحكم في عدد الكلمات المطلوبة\n• احفظ النتائج في ملف\n\nاختر خياراً من الأسفل:",
        'main_menu_word_gen': "📇 القائمة الرئيسية لمولد الكلمات\n\nماذا تريد أن تفعل؟",
        'generate_by_length': "📝 إنشاء حسب الطول",
        'generate_by_formula': "⚙️ إنشاء حسب المعادلة",
        'ask_length': "من فضلك أدخل طول الكلمة (عدد الأحرف):\n\nمثال: 5 للكلمات المكونة من 5 أحرف (1-20)",
        'ask_formula': "أدخل نمط المعادلة:\n\nصيغة المعادلة:\n• x = أي حرف\n• \"نص\" = نص ثابت (استخدم علامات التنصيص)\n• 0 = أي رمز أو رقم\n• رقم = يجب أن يكون هذا الرقم\n\nأمثلة:\n• \"ا\"xxx\"ة\" → كلمات من 5 أحرف تبدأ بـ ا وتنتهي بـ ة\n• xx\"و\"x → كلمات من 4 أحرف مع 'و' كالحرف الثالث\n• \"ال\"xxx → كلمات من 5 أحرف تبدأ بـ 'ال'\n• xx0x → كلمات من 4 أحرف مع رمز/رقم كالحرف الثالث\n\nأدخل معادلتك:",
        'ask_count_words': "كم كلمة تريد؟ (1-500)",
        'invalid_word_length': "🚫 من فضلك أدخل رقماً صحيحاً بين 1 و 20.",
        'invalid_word_count': "🚫 من فضلك أدخل رقماً صحيحاً بين 1 و 500.",
        'invalid_formula': "🚫 صيغة المعادلة غير صحيحة. استخدم علامات التنصيص للنص الثابت و x للأحرف المتغيرة. مثال: \"ا\"xxx\"ة\"",
        'generating_words': "⏳ جاري إنشاء الكلمات... من فضلك انتظر",
        'no_words_found': "😔 لم يتم العثور على كلمات تطابق معاييرك. جرب مواصفات مختلفة.",
        'results_header': "✅ تم العثور على {count} كلمة:\n\n",
        'download_words_btn': "💾 تحميل الكلمات",
        'show_more': "📖 عرض المزيد",
        'word_file_created': "📁 تم حفظ النتائج في الملف",
        'word_error_creating_file': "❌ خطأ في إنشاء الملف"
    }
}


# --- Helper function to get translated text ---
def get_text(context: ContextTypes.DEFAULT_TYPE, key: str, **kwargs) -> str:
    lang = context.user_data.get('language', 'en')
    text = translations.get(lang, translations['en']).get(key, f"Translation missing for '{key}' in '{lang}'")
    return text.format(**kwargs)

# Helper function to escape characters for MarkdownV2
def escape_markdown_v2(text: str) -> str:
    """Helper function to escape characters for MarkdownV2."""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    text = text.replace('\\', '\\\\')
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


# --- Helper Functions for Keyboards ---
def get_main_menu_keyboard(context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(get_text(context, 'generate_username_btn'), callback_data='generate_username')],
        [InlineKeyboardButton(get_text(context, 'generate_word_btn'), callback_data='generate_word')],
        [InlineKeyboardButton(get_text(context, 'bulk_check_btn'), callback_data='bulk')],
        [InlineKeyboardButton(get_text(context, 'how_to_btn'), callback_data='how_to')],
        [InlineKeyboardButton(get_text(context, 'language_btn'), callback_data='set_language')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_word_gen_menu_keyboard(context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(get_text(context, 'generate_by_length'), callback_data='word_gen_length')],
        [InlineKeyboardButton(get_text(context, 'generate_by_formula'), callback_data='word_gen_formula')],
        [InlineKeyboardButton(get_text(context, 'back_btn'), callback_data='back_to_main_menu')],
        [InlineKeyboardButton(get_text(context, 'stop_btn'), callback_data='stop_processing')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_stop_and_back_keyboard(context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(get_text(context, 'back_btn'), callback_data='back_to_main_menu')],
        [InlineKeyboardButton(get_text(context, 'stop_btn'), callback_data='stop_processing')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_result_screen_keyboard(context: ContextTypes.DEFAULT_TYPE, for_words: bool = False):
    if for_words:
        keyboard = [
            [InlineKeyboardButton(get_text(context, 'download_words_btn'), callback_data='download_words')],
            [InlineKeyboardButton(get_text(context, 'back_btn'), callback_data='back_to_word_gen_menu')],
            [InlineKeyboardButton(get_text(context, 'stop_btn'), callback_data='stop_processing')]
        ]
    else: # For username generation
        keyboard = [
            [InlineKeyboardButton(get_text(context, 'download_available_btn'), callback_data='download_available')],
            [InlineKeyboardButton(get_text(context, 'download_all_checked_btn'), callback_data='download_all_checked')],
            [InlineKeyboardButton(get_text(context, 'back_btn'), callback_data='back_to_main_menu')],
            [InlineKeyboardButton(get_text(context, 'stop_btn'), callback_data='stop_processing')]
        ]
    return InlineKeyboardMarkup(keyboard)

def get_language_keyboard():
    keyboard = [
        [InlineKeyboardButton("English", callback_data='lang_en')],
        [InlineKeyboardButton("العربية", callback_data='lang_ar')],
        [InlineKeyboardButton("⬅️ Back", callback_data='back_to_main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)


# --- Core Logic Functions for Username Generation ---

def is_valid_username(username: str) -> bool:
    if not (MIN_USERNAME_LENGTH <= len(username) <= MAX_USERNAME_LENGTH):
        return False
    if not username[0].isalpha():
        return False
    if not all(c.isalnum() or c == '_' for c in username):
        return False
    return True

def is_valid_pattern_for_generation(pattern: str) -> bool:
    return bool(re.search(r'"[^"]*"|x', pattern))

async def generate_usernames(pattern: str, num_variations_to_try: int = 200, context: ContextTypes.DEFAULT_TYPE = None) -> list[str]:
    letters_digits = string.ascii_lowercase + string.digits + '_'
    generated = set()
    attempts = 0
    max_attempts = num_variations_to_try * 20

    parsed_pattern_parts = []
    regex_tokenizer = re.compile(r'"([^"]*)"|(x+)|([^"x]+)')

    for match in regex_tokenizer.finditer(pattern):
        if match.group(1) is not None:
            parsed_pattern_parts.append(('fixed', match.group(1)))
        elif match.group(2) is not None:
            parsed_pattern_parts.append(('placeholder_block', len(match.group(2))))
        elif match.group(3) is not None:
            parsed_pattern_parts.append(('fixed', match.group(3)))

    logger.info(f"Pattern parsed for generation: {parsed_pattern_parts}")

    has_variable_parts = any(part[0] == 'placeholder_block' for part in parsed_pattern_parts)
    if not has_variable_parts and not parsed_pattern_parts:
        logger.warning(f"Pattern '{pattern}' contains no placeholders or fixed parts for generation.")
        return []

    lang = context.user_data.get('language', 'en') if context else 'en'
    fallback_words = FALLBACK_WORDS_AR if lang == 'ar' else FALLBACK_WORDS_EN

    api_seed_words = []
    if lang == 'en':
        try:
            async with httpx.AsyncClient() as client:
                api_url = "https://random-word-api.vercel.app/api"
                params = {"words": 200}
                response = await client.get(api_url, params=params, timeout=7)
                response.raise_for_status()
                api_seed_words = response.json()
                logger.info(f"Fetched {len(api_seed_words)} words from API for pattern generation.")
        except httpx.RequestError as e:
            logger.error(f"HTTPX Request Error fetching words from API: {e}. Using fallback words.")
        except Exception as e:
            logger.error(f"Unexpected error fetching words from API: {e}. Using fallback words.")

    current_seed_words = api_seed_words + fallback_words
    current_seed_words = list(set(current_seed_words))
    random.shuffle(current_seed_words)

    while len(generated) < num_variations_to_try and attempts < max_attempts:
        current_username_parts = []
        seed_word_used_for_first_x_block = False

        for idx, (part_type, content) in enumerate(parsed_pattern_parts):
            if part_type == 'fixed':
                current_username_parts.append(content)
            elif part_type == 'placeholder_block':
                block_len = content

                previous_part_was_fixed = (idx > 0 and parsed_pattern_parts[idx-1][0] == 'fixed')

                is_first_relevant_x_block = (idx == 0 or previous_part_was_fixed) and \
                                            not seed_word_used_for_first_x_block and \
                                            current_seed_words

                if is_first_relevant_x_block:
                    chosen_word = None
                    prefix_for_word_gen = ""
                    if previous_part_was_fixed:
                        prefix_for_word_gen = parsed_pattern_parts[idx-1][1]
                        if current_username_parts and current_username_parts[-1] == prefix_for_word_gen:
                            current_username_parts.pop()

                    candidate_words_for_block = []
                    for word in current_seed_words:
                        word_lower = word.lower()
                        prefix_lower = prefix_for_word_gen.lower()

                        if word_lower.startswith(prefix_lower) and word[0].isalpha():
                            remaining_word_len_from_word = len(word) - len(prefix_for_word_gen)

                            remaining_pattern_min_len = 0
                            for subsequent_part_type, subsequent_content in parsed_pattern_parts[idx+1:]:
                                if subsequent_part_type == 'fixed':
                                    remaining_pattern_min_len += len(subsequent_content)
                                elif subsequent_part_type == 'placeholder_block':
                                    remaining_pattern_min_len += 1

                            hypothetical_total_len = len("".join(current_username_parts)) + len(word) + max(0, block_len - remaining_word_len_from_word) + remaining_pattern_min_len

                            if MIN_USERNAME_LENGTH <= hypothetical_total_len <= MAX_USERNAME_LENGTH:
                                candidate_words_for_block.append((abs(remaining_word_len_from_word - block_len), word))

                    if candidate_words_for_block:
                        candidate_words_for_block.sort(key=lambda x: x[0])
                        best_fit_diff = candidate_words_for_block[0][0]
                        best_fit_words = [w for diff, w in candidate_words_for_block if diff == best_fit_diff]
                        chosen_word = random.choice(best_fit_words)
                    elif current_seed_words:
                        any_valid_start_words = []
                        for word in current_seed_words:
                            if word[0].isalpha():
                                hypothetical_total_len = len("".join(current_username_parts)) + len(word) + remaining_pattern_min_len
                                if MIN_USERNAME_LENGTH <= hypothetical_total_len <= MAX_USERNAME_LENGTH:
                                    any_valid_start_words.append(word)
                        if any_valid_start_words:
                            chosen_word = random.choice(any_valid_start_words)

                    if chosen_word:
                        current_username_parts.append(chosen_word)
                        seed_word_used_for_first_x_block = True

                        chars_to_fill_in_block = block_len - (len(chosen_word) - len(prefix_for_word_gen))
                        if chars_to_fill_in_block > 0:
                            for _ in range(chars_to_fill_in_block):
                                current_username_parts.append(random.choice(letters_digits))
                    else:
                        if previous_part_was_fixed:
                            current_username_parts.append(prefix_for_word_gen)

                        for _ in range(block_len):
                            if idx == 0 and not current_username_parts:
                                current_username_parts.append(random.choice(string.ascii_lowercase))
                            else:
                                current_username_parts.append(random.choice(letters_digits))

                else:
                    for _ in range(block_len):
                        current_username_parts.append(random.choice(letters_digits))

        final_uname = "".join(current_username_parts)

        if is_valid_username(final_uname):
            generated.add(final_uname)
        attempts += 1

    return list(generated)

async def check_username_availability(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str) -> tuple[bool, str, str | None]:
    if not is_valid_username(username):
        logger.warning(f"Invalid username format (pre-API check): {username}")
        return False, username, None

    try:
        chat = await context.bot.get_chat(f"@{username}")
        logger.info(f"Username @{username} recognized by Telegram API (Chat ID: {chat.id}, Type: {chat.type}). Considered taken/reserved.")
        return False, username, f"https://t.me/{chat.username}" if chat.username else None

    except TimedOut as e:
        retry_after = e.retry_after
        logger.warning(f"FLOODWAIT: Hit flood control for @{username}. Retrying in {retry_after} seconds.")
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=get_text(context, 'flood_wait_message', retry_after=retry_after)
            )
        except Exception as send_e:
            logger.error(f"Failed to send flood_wait_message: {send_e}")
        await asyncio.sleep(retry_after)
        return await check_username_availability(update, context, username)
    except BadRequest as e:
        error_message = str(e).lower()
        if "username not found" in error_message or "chat not found" in error_message:
            logger.info(f"Username @{username} is likely available (BadRequest: '{error_message}').")
            return True, username, f"https://t.me/{username}"
        else:
            logger.error(f"Telegram API BadRequest for {username} (NOT available, reason: '{error_message}').")
            return False, username, None
    except Exception as e:
        logger.error(f"Unexpected error checking username {username} (assuming NOT available): {e}")
        return False, username, None

async def display_results(update: Update, context: ContextTypes.DEFAULT_TYPE, all_results: list[dict], pattern: str = None, is_bulk: bool = False):
    available_names_info = [r for r in all_results if r['available']]
    taken_names_info = [r for r in all_results if not r['available']]

    context.user_data['last_available_names'] = [r['username'] for r in available_names_info]
    context.user_data['last_all_checked_results'] = all_results

    text_parts = []
    if pattern:
        escaped_pattern_display = escape_markdown_v2(pattern)
        text_parts.append(get_text(context, 'checked_variations', total_checked=len(all_results), pattern=escaped_pattern_display))
    else:
        text_parts.append(get_text(context, 'checked_list_usernames', total_checked=len(all_results)))


    def format_names_for_display(name_objects: list[dict]) -> list[str]:
        formatted = []
        for item in name_objects:
            escaped_username = escape_markdown_v2(item['username'])
            if item['link']:
                formatted.append(f"[`@{escaped_username}`]({item['link']})")
            else:
                formatted.append(f"`@{escaped_username}`")
        return formatted

    if available_names_info:
        text_parts.append(get_text(context, 'available_names', count=len(available_names_info)))
        display_available = format_names_for_display(available_names_info)
        text_parts.append("\n".join(display_available))
        num_to_generate = context.user_data.get('num_to_generate_display', len(available_names_info))
        if len(available_names_info) > num_to_generate:
            remaining = len(available_names_info) - num_to_generate
            text_parts.append(f"...and {remaining} more available names.")
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
        if available_names_info and not taken_names_info:
             text_parts.append(get_text(context, 'all_generated_available'))


    final_text = "\n".join(text_parts)

    if len(final_text) > 4000:
        if is_bulk:
            final_text = get_text(context, 'list_result_too_long', total_checked=len(all_results), available_count=len(available_names_info), taken_count=len(taken_names_info))
        else:
            final_text = get_text(context, 'result_too_long', total_checked=len(all_results), available_count=len(available_names_info), taken_count=len(taken_names_info))

    await update.effective_chat.send_message(final_text, parse_mode='Markdown', reply_markup=get_result_screen_keyboard(context))


async def process_check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    usernames: list[str],
    pattern: str = None,
    is_bulk: bool = False
):
    all_results = []
    available_count = 0
    taken_count = 0
    chat_id = update.effective_chat.id

    loop = asyncio.get_running_loop()
    last_update_time = loop.time()
    progress_msg_id = None

    warning_text = ""
    if len(usernames) > 100:
        warning_text = get_text(context, 'large_request_warning') + "\n\n"

    try:
        escaped_pattern_for_init_msg = escape_markdown_v2(pattern) if pattern else ""
        initial_message = await update.message.reply_text(
            warning_text + get_text(context, 'searching_names', count=len(usernames), pattern=escaped_pattern_for_init_msg),
            parse_mode='Markdown',
            reply_markup=get_stop_and_back_keyboard(context)
        )
        progress_msg_id = initial_message.message_id
        context.user_data['progress_message_id'] = progress_msg_id
        context.user_data['stop_requested'] = False
    except Exception as e:
        logger.error(f"Failed to send initial progress message: {e}")
        await update.effective_chat.send_message(get_text(context, 'operation_cancelled'))
        return ConversationHandler.END


    check_delay = context.user_data.get('check_delay', 0.05)

    try:
        for i, uname in enumerate(usernames):
            if context.user_data.get('stop_requested'):
                logger.info("Stop requested by user. Breaking loop.")
                break

            is_available, username_str, link = await check_username_availability(update, context, uname)
            all_results.append({'username': username_str, 'available': is_available, 'link': link})

            if is_available:
                try:
                    escaped_username_str = escape_markdown_v2(username_str)
                    msg_text = get_text(context, 'found_available_immediate',
                                         username=f"[`@{escaped_username_str}`]({link})" if link else f"`@{escaped_username_str}`")
                    await update.effective_chat.send_message(msg_text, parse_mode='Markdown')
                except Exception as e:
                    logger.warning(f"Failed to send immediate available name update: {e}")

            if is_available:
                available_count += 1
            else:
                taken_count += 1

            current_time = loop.time()
            if (i + 1) % UPDATE_INTERVAL_COUNT == 0 or (current_time - last_update_time) >= UPDATE_INTERVAL_SECONDS:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_msg_id,
                        text=get_text(context, 'checking_progress',
                                      current_checked=i+1,
                                      total_to_check=len(usernames),
                                      available_count=available_count,
                                      taken_count=taken_count,
                                      remaining_count=len(usernames)-(i+1)),
                        parse_mode='Markdown',
                        reply_markup=get_stop_and_back_keyboard(context)
                    )
                    last_update_time = current_time
                except Exception as e:
                    logger.warning(f"Failed to update progress message: {e}")

            try:
                await asyncio.sleep(check_delay)
            except asyncio.CancelledError:
                logger.info("Processing task was cancelled during sleep.")
                break

    except asyncio.CancelledError:
        logger.info("Process check task was externally cancelled.")
    finally:
        if all_results:
            await display_results(update, context, all_results, pattern=pattern, is_bulk=is_bulk)
        else:
            await update.effective_chat.send_message(get_text(context, 'operation_cancelled'))

    return ConversationHandler.END


# --- Core Logic Functions for Word Generation ---

def filter_words_by_length(words: Set[str], length: int) -> List[str]:
    """Filter words by exact length"""
    return [word for word in words if len(word) == length]

def parse_formula_pattern(formula: str) -> Dict:
    """Parse formula pattern like 'L'xxx'e' or xx'o'x"""
    try:
        constraints = []
        current_pos = 0
        total_length = 0
        i = 0
        while i < len(formula):
            if formula[i] == '"':
                j = i + 1
                while j < len(formula) and formula[j] != '"':
                    j += 1
                if j < len(formula):
                    fixed_text = formula[i+1:j].lower()
                    constraints.append({
                        'type': 'fixed_text',
                        'position': current_pos,
                        'text': fixed_text
                    })
                    current_pos += len(fixed_text)
                    total_length += len(fixed_text)
                    i = j + 1
                else:
                    return None # Unclosed quote
            elif formula[i].lower() == 'x':
                current_pos += 1
                total_length += 1
                i += 1
            elif formula[i].isdigit():
                constraints.append({
                    'type': 'character_type',
                    'position': current_pos,
                    'char_type': 'digit'
                })
                current_pos += 1
                total_length += 1
                i += 1
            elif formula[i] == '0':
                constraints.append({
                    'type': 'character_type',
                    'position': current_pos,
                    'char_type': 'symbol_or_digit'
                })
                current_pos += 1
                total_length += 1
                i += 1
            else:
                i += 1 # Skip unknown characters
        return {
            'type': 'formula',
            'length': total_length,
            'constraints': constraints
        }
    except Exception as e:
        logger.error(f"Error parsing formula pattern '{formula}': {e}")
        return None

def filter_words_by_pattern(words: Set[str], pattern_dict: Dict) -> List[str]:
    """Filter words based on pattern dictionary"""
    if not pattern_dict:
        return []
    filtered_words = []
    for word in words:
        if pattern_dict['type'] == 'formula':
            if matches_formula(word, pattern_dict):
                filtered_words.append(word)
    return filtered_words

def matches_formula(word: str, pattern_dict: Dict) -> bool:
    """Check if word matches formula pattern"""
    if len(word) != pattern_dict['length']:
        return False
    for constraint in pattern_dict['constraints']:
        if constraint['type'] == 'fixed_text':
            start_pos = constraint['position']
            end_pos = start_pos + len(constraint['text'])
            if end_pos > len(word) or word[start_pos:end_pos] != constraint['text']:
                return False
        elif constraint['type'] == 'character_type':
            pos = constraint['position']
            if pos >= len(word):
                return False
            char = word[pos]
            if constraint['char_type'] == 'digit':
                if not char.isdigit():
                    return False
            elif constraint['char_type'] == 'symbol_or_digit':
                if char.isalpha(): # It must NOT be an alphabet char
                    return False
    return True

def generate_words(length: int = None, formula: str = None, count: int = 10, language: str = 'en') -> List[str]:
    """Generate words based on criteria"""
    if language == 'ar':
        words = ARABIC_WORDS.copy()
    else:
        words = ENGLISH_WORDS.copy()

    if length:
        words = set(filter_words_by_length(words, length))

    if formula:
        pattern_dict = parse_formula_pattern(formula)
        if pattern_dict:
            words = set(filter_words_by_pattern(words, pattern_dict))
        else:
            logger.warning(f"Invalid formula '{formula}', skipping formula filtering.")

    word_list = list(words)
    random.shuffle(word_list)
    return word_list[:count]


# --- Main Handler Functions ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'language' not in context.user_data:
        context.user_data['language'] = 'en'
    context.user_data['stop_requested'] = False
    await update.message.reply_text(get_text(context, 'welcome'), reply_markup=get_main_menu_keyboard(context))
    return INITIAL_MENU

async def handle_button_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'generate_username':
        await query.edit_message_text(get_text(context, 'how_many_names'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_USERNAME_COUNT
    elif query.data == 'generate_word':
        await query.edit_message_text(get_text(context, 'main_menu_word_gen'), reply_markup=get_word_gen_menu_keyboard(context))
        return ASK_WORD_LENGTH
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

    # File download callbacks (for username results)
    elif query.data == 'download_available':
        if 'last_available_names' in context.user_data and context.user_data['last_available_names']:
            await send_names_as_file(context, update.effective_chat.id, context.user_data['last_available_names'], "available_usernames.txt")
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
                clean_status = status_text.replace('✅ Available (', '').replace('❌ Taken (', '').replace('):', '').strip()
                formatted_results.append(f"{item['username']} ({clean_status})")
            await send_names_as_file(context, update.effective_chat.id, formatted_results, "all_checked_usernames.txt")
        else:
            await query.message.reply_text(get_text(context, 'no_names_to_save', filename="all_checked_usernames.txt"))
        await query.edit_message_text(get_text(context, 'welcome'), reply_markup=get_main_menu_keyboard(context))
        return INITIAL_MENU

    # Navigation callbacks
    elif query.data == 'back_to_main_menu':
        context.user_data['stop_requested'] = True
        await query.edit_message_text(
            get_text(context, 'welcome'),
            reply_markup=get_main_menu_keyboard(context)
        )
        return INITIAL_MENU
    elif query.data == 'back_to_word_gen_menu':
        await query.edit_message_text(get_text(context, 'main_menu_word_gen'), reply_markup=get_word_gen_menu_keyboard(context))
        return ASK_WORD_LENGTH

    elif query.data == 'stop_processing':
        await stop_processing_callback(update, context)
        return ConversationHandler.END

    # Word generation specific callbacks
    elif query.data == 'word_gen_length':
        await query.edit_message_text(get_text(context, 'ask_length'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_WORD_LENGTH
    elif query.data == 'word_gen_formula':
        await query.edit_message_text(get_text(context, 'ask_formula'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_WORD_FORMULA
    elif query.data == 'download_words': # For word generation results
        if 'last_generated_words' in context.user_data and context.user_data['last_generated_words']:
            await send_names_as_file(context, update.effective_chat.id, context.user_data['last_generated_words'], "generated_words.txt")
        else:
            await query.message.reply_text(get_text(context, 'no_names_to_save', filename="generated_words.txt"))
        await query.edit_message_text(get_text(context, 'main_menu_word_gen'), reply_markup=get_word_gen_menu_keyboard(context))
        return ASK_WORD_LENGTH

    return INITIAL_MENU

async def stop_processing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer(text=get_text(context, 'stopping_process_ack'))

    context.user_data['stop_requested'] = True

    if 'processing_task' in context.user_data and not context.user_data['processing_task'].done():
        context.user_data['processing_task'].cancel()
        logger.info("Attempted to cancel the ongoing process_check task.")
        try:
            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    if 'progress_message_id' in context.user_data:
        try:
            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=context.user_data['progress_message_id'],
                text=get_text(context, 'stopping_process_ack'),
                reply_markup=None
            )
        except Exception as e:
            logger.warning(f"Failed to edit message to acknowledge stop: {e}")

    try:
        await query.message.reply_text(
            get_text(context, 'welcome'),
            reply_markup=get_main_menu_keyboard(context)
        )
    except Exception as e:
        logger.error(f"Failed to send main menu after stop: {e}")

    return ConversationHandler.END


async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang_code = query.data.split('_')[1]
    context.user_data['language'] = lang_code

    await query.edit_message_text(get_text(context, 'language_set'), reply_markup=get_main_menu_keyboard(context))
    return INITIAL_MENU


# --- Handlers for Username Generation Flow ---
async def handle_username_count_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text.strip())
        if not (1 <= count <= 500):
            await update.message.reply_text(get_text(context, 'invalid_number'), reply_markup=get_stop_and_back_keyboard(context))
            return ASK_USERNAME_COUNT

        context.user_data['num_to_generate_display'] = count
        await update.message.reply_text(get_text(context, 'send_pattern'), parse_mode='Markdown', reply_markup=get_stop_and_back_keyboard(context))
        return ASK_PATTERN
    except ValueError:
        await update.message.reply_text(get_text(context, 'invalid_number'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_USERNAME_COUNT

async def handle_pattern_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = update.message.text.strip()
    if not pattern or not is_valid_pattern_for_generation(pattern):
        await update.message.reply_text(get_text(context, 'invalid_pattern'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_PATTERN

    context.user_data['pattern'] = pattern
    await update.message.reply_text(get_text(context, 'ask_delay'), reply_markup=get_stop_and_back_keyboard(context))
    return ASK_DELAY

async def handle_delay_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        delay = float(update.message.text.strip())
        if delay < 0:
            raise ValueError
        context.user_data['check_delay'] = delay

        pattern = context.user_data['pattern']
        num_to_display = context.user_data.get('num_to_generate_display', 20)

        generated_names = await generate_usernames(pattern, num_to_display, context)

        if not generated_names:
            await update.message.reply_text(get_text(context, 'no_available_names'), reply_markup=get_stop_and_back_keyboard(context))
            return INITIAL_MENU

        task = asyncio.create_task(
            process_check(
                update=update,
                context=context,
                usernames=generated_names,
                pattern=pattern,
                is_bulk=False
            )
        )
        context.user_data['processing_task'] = task
        return ASK_DELAY

    except ValueError:
        await update.message.reply_text(get_text(context, 'invalid_delay'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_DELAY

async def bulk_list_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [n.strip() for n in update.message.text.splitlines() if n.strip()]
    if not names:
        await update.message.reply_text(get_text(context, 'no_usernames_provided'), reply_markup=get_stop_and_back_keyboard(context))
        return BULK_LIST

    task = asyncio.create_task(
        process_check(
            update=update,
            context=context,
            usernames=names,
            pattern=None,
            is_bulk=True
        )
    )
    context.user_data['processing_task'] = task
    return BULK_LIST


# --- Handlers for Word Generation Flow ---
async def handle_word_length_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        length = int(update.message.text.strip())
        if not (1 <= length <= 20):
            await update.message.reply_text(get_text(context, 'invalid_word_length'), reply_markup=get_stop_and_back_keyboard(context))
            return ASK_WORD_LENGTH

        context.user_data['word_length'] = length
        await update.message.reply_text(get_text(context, 'ask_count_words'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_WORD_COUNT
    except ValueError:
        await update.message.reply_text(get_text(context, 'invalid_word_length'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_WORD_LENGTH

async def handle_word_formula_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    formula = update.message.text.strip()
    pattern_dict = parse_formula_pattern(formula)
    if not pattern_dict:
        await update.message.reply_text(get_text(context, 'invalid_formula'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_WORD_FORMULA

    context.user_data['word_formula'] = formula
    await update.message.reply_text(get_text(context, 'ask_count_words'), reply_markup=get_stop_and_back_keyboard(context))
    return ASK_WORD_COUNT

async def handle_word_count_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text.strip())
        if not (1 <= count <= 500):
            await update.message.reply_text(get_text(context, 'invalid_word_count'), reply_markup=get_stop_and_back_keyboard(context))
            return ASK_WORD_COUNT

        context.user_data['word_count'] = count

        await update.message.reply_text(get_text(context, 'generating_words'))

        length = context.user_data.get('word_length')
        formula = context.user_data.get('word_formula')
        words = generate_words(length=length, formula=formula, count=count, language=context.user_data.get('language', 'en'))

        if words:
            context.user_data['last_generated_words'] = words
            results_text = get_text(context, 'results_header').format(count=len(words))
            results_text += '\n'.join(f"• {word}" for word in words[:20])
            if len(words) > 20:
                results_text += f"\n\n... {len(words) - 20} " + get_text(context, 'show_more')

            await update.message.reply_text(
                results_text,
                reply_markup=get_result_screen_keyboard(context, for_words=True)
            )
            # Clear temporary word gen data
            context.user_data.pop('word_length', None)
            context.user_data.pop('word_formula', None)
            context.user_data.pop('word_count', None)
            return SHOW_WORD_RESULTS
        else:
            await update.message.reply_text(
                get_text(context, 'no_words_found'),
                reply_markup=get_word_gen_menu_keyboard(context)
            )
            # Clear temporary word gen data
            context.user_data.pop('word_length', None)
            context.user_data.pop('word_formula', None)
            context.user_data.pop('word_count', None)
            return ASK_WORD_LENGTH

    except ValueError:
        await update.message.reply_text(get_text(context, 'invalid_word_count'), reply_markup=get_stop_and_back_keyboard(context))
        return ASK_WORD_COUNT


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['stop_requested'] = True
    if 'processing_task' in context.user_data and not context.user_data['processing_task'].done():
        context.user_data['processing_task'].cancel()
        logger.info("Attempted to cancel processing task via /cancel command.")

    await update.message.reply_text(get_text(context, 'operation_cancelled'), reply_markup=get_main_menu_keyboard(context))
    return ConversationHandler.END


async def send_names_as_file(context: ContextTypes.DEFAULT_TYPE, chat_id: int, names_list: list[str], filename: str):
    if not names_list:
        await context.bot.send_message(chat_id=chat_id, text=get_text(context, 'no_names_to_save', filename=filename))
        return

    file_content = "\n".join(names_list)
    file_stream = io.BytesIO(file_content.encode('utf-8'))
    file_stream.name = filename

    try:
        if filename == "generated_words.txt":
            caption_key = 'word_file_created'
        else:
            caption_key = 'file_created'
        await context.bot.send_document(chat_id=chat_id, document=InputFile(file_stream), caption=get_text(context, caption_key))
        logger.info(f"Sent {filename} to chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send document {filename} to chat {chat_id}: {e}")
        await context.bot.send_message(chat_id=chat_id, text=get_text(context, 'failed_to_send_file', error=str(e)))


if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            INITIAL_MENU: [CallbackQueryHandler(handle_button_callbacks)],

            # States for Username Generation
            ASK_USERNAME_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username_count_input),
                CallbackQueryHandler(handle_button_callbacks)
            ],
            ASK_PATTERN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pattern_input),
                CallbackQueryHandler(handle_button_callbacks)
            ],
            ASK_DELAY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delay_input),
                CallbackQueryHandler(handle_button_callbacks)
            ],
            BULK_LIST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_list_input),
                CallbackQueryHandler(handle_button_callbacks)
            ],
            HOW_TO_INFO: [
                CallbackQueryHandler(handle_button_callbacks)
            ],
            SET_LANGUAGE: [
                CallbackQueryHandler(handle_button_callbacks)
            ],

            # States for Word Generation (New)
            ASK_WORD_LENGTH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_word_length_input),
                CallbackQueryHandler(handle_button_callbacks)
            ],
            ASK_WORD_FORMULA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_word_formula_input),
                CallbackQueryHandler(handle_button_callbacks)
            ],
            ASK_WORD_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_word_count_input),
                CallbackQueryHandler(handle_button_callbacks)
            ],
            SHOW_WORD_RESULTS: [
                CallbackQueryHandler(handle_button_callbacks)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(stop_processing_callback, pattern="^stop_processing$"),
            CallbackQueryHandler(handle_button_callbacks)
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

