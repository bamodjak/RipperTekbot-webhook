import logging
import os
import random
import string
import asyncio
import re
import tempfile # For creating temporary files
from typing import List, Dict, Set, Optional

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import TimedOut, RetryAfter, TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# --- Configuration ---
# IMPORTANT: Get your bot token from BotFather.
# Set TELEGRAM_TOKEN, WEBHOOK_URL, PORT, and ADMIN_ID as environment variables on your hosting platform (e.g., Railway).
# Example for Railway:
# TELEGRAM_TOKEN = your_actual_bot_token_here
# WEBHOOK_URL = https://your-railway-project-domain.railway.app
# PORT = 8000 (or 8443, or whatever port Railway assigns/expects for your app)
# ADMIN_ID = your_numeric_telegram_user_id (e.g., 123456789)

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000)) # Default to 8000 if PORT env var is not set
ADMIN_ID = os.getenv("ADMIN_ID") # Read admin ID from environment variable

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN environment variable not set! Please set it on Railway.")
if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL environment variable not set! Please set it on Railway.")
if not ADMIN_ID:
    logger.warning("ADMIN_ID environment variable is not set. Admin features will be unavailable.")
    ADMIN_ID = None # Ensure it's None if not set, for checks later
else:
    try:
        ADMIN_ID = int(ADMIN_ID) # Convert to int for comparison
    except ValueError:
        logger.error(f"ADMIN_ID environment variable '{os.getenv('ADMIN_ID')}' is not a valid numeric ID. Admin features will be unavailable.")
        ADMIN_ID = None


# States for ConversationHandler
(INITIAL_MENU, ASK_USERNAME_COUNT, ASK_PATTERN, ASK_DELAY, BULK_LIST,
 HOW_TO_INFO, SET_LANGUAGE, ASK_WORD_LENGTH, ASK_WORD_COUNT,
 ASK_BOT_SEARCH) = range(10)

# --- Data for Simulation and Generation ---

# Hardcoded lists for word generation (since external libraries might not be available)
ENGLISH_WORDS = {
    'apple', 'banana', 'cherry', 'date', 'elder', 'fig', 'grape', 'honey', 'kiwi', 'lemon',
    'mango', 'nut', 'orange', 'pear', 'quince', 'raspberry', 'strawberry', 'tangerine', 'ume', 'vanilla',
    'book', 'school', 'house', 'pen', 'paper', 'student', 'teacher', 'lesson', 'exam', 'success',
    'love', 'peace', 'hope', 'light', 'life', 'work', 'time', 'day', 'night', 'morning',
    'evening', 'sun', 'moon', 'star', 'sea', 'mountain', 'tree', 'flower', 'bird', 'fish',
    'food', 'water', 'bread', 'meat', 'fruit', 'vegetable', 'milk', 'tea', 'coffee', 'juice',
    'father', 'mother', 'son', 'daughter', 'brother', 'sister', 'grandfather', 'grandmother', 'uncle', 'aunt',
    'friend', 'neighbor', 'guest', 'doctor', 'engineer', 'farmer', 'trader'
}

ARABIC_WORDS = {
    'كتاب', 'مدرسة', 'بيت', 'قلم', 'ورقة', 'طالب', 'معلم', 'درس', 'امتحان', 'نجاح',
    'حب', 'سلام', 'أمل', 'نور', 'حياة', 'عمل', 'وقت', 'يوم', 'ليلة', 'صباح',
    'مساء', 'شمس', 'قمر', 'نجم', 'بحر', 'جبل', 'شجرة', 'زهرة', 'طائر', 'سمك',
    'طعام', 'ماء', 'خبز', 'لحم', 'فاكهة', 'خضار', 'لبن', 'شاي', 'قهوة', 'عصير',
    'أب', 'أم', 'ابن', 'ابنة', 'أخ', 'أخت', 'جد', 'جدة', 'عم', 'خال',
    'صديق', 'جار', 'ضيف', 'طبيب', 'مهندس', 'معلم', 'طالب', 'عامل', 'تاجر', 'فلاح'
}

# Simulated "taken" usernames for availability check
# These are case-insensitive for simulation purposes.
SIMULATED_TAKEN_USERNAMES = {
    "admin", "support", "telegram", "user123", "testbot", "john_doe", "jane_smith",
    "cool_user", "best_name", "arabic_user", "english_word", "rippertekbot", "officialbot",
    "botfather", "channelbot", "groupbot", "superbot", "mytestbot", "test_bot_1",
    "available_user_taken", "taken_name_example"
}

# Constants
MIN_USERNAME_LENGTH = 5
MAX_USERNAME_LENGTH = 32
PLACEHOLDER_CHAR = 'x' # Used for random character in patterns

# --- Translations ---
translations = {
    'en': {
        'welcome': "🤖 Welcome to RipperTek Bot! Please choose an option:",
        'generate_username_btn': "🔤 Generate Username",
        'generate_word_btn': "📚 Generate Words",
        'bulk_check_btn': "📄 Bulk Check List",
        'bot_search_btn': "🤖 Bot Search",
        'how_to_btn': "❓ How To Use",
        'language_btn': "🌐 Language",
        'home_btn': "🏠 Home",
        'english_btn': "🇺🇸 English",
        'arabic_btn': "🇸🇦 العربية",
        'language_selection': "Please choose your language:",
        'language_set': "✅ Language set to English.",
        'how_many_names': "How many usernames would you like to generate? (1-500)",
        'invalid_number': "❌ Please enter a number between 1 and 500.",
        'send_pattern': "📝 Send a pattern (e.g., `user_x_x_x` where 'x' = random chars/digits):\n\n💡 Tips:\n• Use quotes for fixed parts: `\"myname\"_x_x`\n• x = random character/digit\n• Keep it 5-32 characters total",
        'invalid_pattern': "❌ Invalid pattern. Please try again.",
        'ask_delay': "⏱️ Enter simulated delay between checks (seconds):\n• 0.1 = 100ms\n• 1.0 = 1 second\n• 0 = no delay\n\n(Note: This is a simulation, not real Telegram API delay)",
        'invalid_delay': "❌ Please enter a valid delay (e.g., 0.1, 1, 5).",
        'searching_names': "🔍 Simulating search for {count} usernames with pattern '{pattern}'...",
        'checking_progress': "⏳ Progress: {current_checked}/{total_to_check}\n✅ Available: {available_count}\n❌ Taken: {taken_count}\n\n📊 Remaining: {remaining_count}",
        'check_complete': "✅ Simulation Complete!\n\n📊 Results:\n• Total checked: {total_checked}\n• Available: {available_count}\n• Taken: {taken_count}",
        'available_usernames': "✅ Simulated Available Usernames:",
        'no_available': "❌ No simulated available usernames found.",
        'send_bulk_list': "📄 Send your list of usernames (one per line, max 500) OR upload a .txt file:\n\n(Note: Availability check is simulated)",
        'invalid_bulk_list': "❌ Invalid list. Please send usernames (one per line, max 500) or upload a valid .txt file.",
        'bulk_checking': "🔍 Simulating check for {count} usernames from your list...",
        'how_to_text': """📖 **How to Use RipperTek Bot**

**Important Note:** Username and bot name availability checks are **simulated** within this bot, as direct real-time checks via Telegram's API are not publicly available.

🔤 **Username Generator:**
• Choose how many to generate (1-500)
• Create patterns with 'x' for random chars/digits
• Set a simulated delay between checks
• Get simulated available usernames

📚 **Word Generator:**
• Generate English or Arabic words
• Choose word length and count
• Perfect for creative projects

📄 **Bulk Check:**
• Send a list of usernames (one per line)
• **OR upload a .txt file containing usernames**
• Simulate availability in bulk
• Get detailed simulated results

🤖 **Bot Search:**
• Search for bot usernames (I will add 'bot' if needed)
• Simulate availability for bot names

💡 **Tips:**
• Use quotes in patterns for fixed text (e.g., `"myname"_x_x`)
• Shorter delays = faster simulation
• Bot names must end with 'bot'""",
        'word_length': "📏 Enter desired word length (3-15 characters) or a pattern (e.g., `app_x_x`):\n\n💡 Tips:\n• Use 'x' for random letters\n• Use quotes for fixed parts: `\"my\"_x_x`",
        'invalid_word_length': "❌ Please enter a length between 3 and 15, or a valid pattern.",
        'word_count': "🔢 How many words to generate? (1-1,000,000)",
        'invalid_word_count': "❌ Please enter a number between 1 and 1,000,000.",
        'generated_words': "📚 Generated Words:",
        'bot_search_prompt': "🤖 Enter bot name to search (without @). I will automatically add 'bot' to the end if it's not already there.\nExample: mycoolbot or just mycool\n\n(Note: Availability check is simulated)",
        'bot_search_results': "🤖 Simulated Bot Search Results for '{name}':",
        'bot_available': "✅ @{name} is simulated available!",
        'bot_taken': "❌ @{name} is simulated taken.",
        'invalid_bot_name': "❌ Invalid bot name. The final name (including 'bot') must be 5-32 characters, alphanumeric + underscores.",
        'rate_limit_warning': "⚠️ Simulated rate limit reached. Pausing for {seconds} seconds...",
        'timeout_error': "⏰ Simulated request timed out. Please try again.",
        'network_error': "🌐 Simulated network error. Please check your connection.",
        'error_occurred': "❌ An error occurred: {error}",
        'operation_cancelled': "Operation cancelled. Returning to main menu.",
        'download_all_usernames_btn': "⬇️ Download All Usernames",
        'download_available_usernames_btn': "⬇️ Download Available Usernames",
        'download_words_btn': "⬇️ Download Words",
        'download_bulk_all_btn': "⬇️ Download All Checked",
        'download_bulk_available_btn': "⬇️ Download Available Only",
        'file_sent': "✅ File sent successfully!",
        'no_data_to_download': "❌ No data to download. Please generate or check first."
    },
    'ar': {
        'welcome': "🤖 مرحباً بك في بوت RipperTek! اختر خياراً:",
        'generate_username_btn': "🔤 إنشاء اسم مستخدم",
        'generate_word_btn': "📚 إنشاء كلمات",
        'bulk_check_btn': "📄 فحص قائمة",
        'bot_search_btn': "🤖 البحث عن بوت",
        'how_to_btn': "❓ كيفية الاستخدام",
        'language_btn': "🌐 اللغة",
        'home_btn': "🏠 الرئيسية",
        'english_btn': "🇺🇸 English",
        'arabic_btn': "🇸🇦 العربية",
        'language_selection': "اختر لغتك:",
        'language_set': "✅ تم تعيين اللغة إلى العربية.",
        'how_many_names': "كم اسم مستخدم تريد إنشاؤه؟ (1-500)",
        'invalid_number': "❌ أدخل رقماً بين 1 و 500.",
        'send_pattern': "📝 أرسل نمطاً (مثال: `user_x_x_x` حيث 'x' = حروف/أرقام عشوائية):\n\n💡 نصائح:\n• استخدم الاقتباس للأجزاء الثابتة: `\"اسمي\"_x_x`\n• x = حرف/رقم عشوائي\n• احتفظ بـ 5-32 حرف إجمالي",
        'invalid_pattern': "❌ نمط غير صحيح. حاول مرة أخرى.",
        'ask_delay': "⏱️ أدخل التأخير المحاكي بين الفحوصات (ثواني):\n• 0.1 = 100 ميلي ثانية\n• 1.0 = ثانية واحدة\n• 0 = بدون تأخير\n\n(ملاحظة: هذا محاكاة، وليس تأخير واجهة برمجة تطبيقات تيليجرام الحقيقي)",
        'invalid_delay': "❌ أدخل تأخيراً صحيحاً (مثال: 0.1، 1، 5).",
        'searching_names': "🔍 محاكاة البحث عن {count} أسماء مستخدمين بالنمط '{pattern}'...",
        'checking_progress': "⏳ التقدم: {current_checked}/{total_to_check}\n✅ متاح: {available_count}\n❌ مأخوذ: {taken_count}\n\n📊 المتبقي: {remaining_count}",
        'check_complete': "✅ اكتملت المحاكاة!\n\n📊 النتائج:\n• إجمالي المفحوص: {total_checked}\n• متاح: {available_count}\n• مأخوذ: {taken_count}",
        'available_usernames': "✅ أسماء المستخدمين المتاحة (محاكاة):",
        'no_available': "❌ لم يتم العثور على أسماء مستخدمين متاحة (محاكاة).",
        'send_bulk_list': "📄 أرسل قائمتك من أسماء المستخدمين (واحد في كل سطر، أقصى 500) أو قم بتحميل ملف .txt:\n\n(ملاحظة: فحص التوفر محاكى)",
        'invalid_bulk_list': "❌ قائمة غير صحيحة. أرسل أسماء مستخدمين (واحد في كل سطر، أقصى 500) أو قم بتحميل ملف .txt صالح.",
        'bulk_checking': "🔍 محاكاة فحص {count} أسماء مستخدمين من قائمتك...",
        'how_to_text': """📖 **كيفية استخدام بوت RipperTek**

**ملاحظة هامة:** فحص توفر أسماء المستخدمين وأسماء البوت **محاكى** داخل هذا البوت، حيث أن الفحوصات المباشرة في الوقت الفعلي عبر واجهة برمجة تطبيقات تيليجرام غير متاحة للعامة.

🔤 **منشئ أسماء المستخدمين:**
• اختر كم تريد إنشاؤه (1-500)
• أنشئ أنماط بـ 'x' للحروف/الأرقام العشوائية
• حدد تأخيراً محاكياً بين الفحوصات
• احصل على أسماء مستخدمين متاحة (محاكاة)

📚 **منشئ الكلمات:**
• أنشئ كلمات إنجليزية أو عربية
• اختر طول الكلمة والعدد
• مثالي للمشاريع الإبداعية

📄 **الفحص المجمع:**
• أرسل قائمة أسماء مستخدمين (واحد في كل سطر)
• **أو قم بتحميل ملف .txt يحتوي على أسماء المستخدمين**
• محاكاة فحص التوفر بالجملة
• احصل على نتائج مفصلة (محاكاة)

🤖 **البحث عن البوت:**
• ابحث عن أسماء البوت (سأضيف 'bot' إذا لزم الأمر)
• محاكاة توفر أسماء البوت

💡 **نصائح:**
• استخدم الاقتباس في الأنماط للنص الثابت (مثال: `"اسمي"_x_x`)
• التأخيرات الأقصر = محاكاة أسرع
• أسماء البوت يجب أن تنتهي بـ 'bot'""",
        'word_length': "📏 أدخل طول الكلمة المطلوب (3-15 حرف) أو نمطاً (مثال: `app_x_x`):\n\n💡 نصائح:\n• استخدم 'x' للحروف العشوائية\n• استخدم الاقتباس للأجزاء الثابتة: `\"اسمي\"_x_x`",
        'invalid_word_length': "❌ أدخل طولاً بين 3 و 15، أو نمطاً صحيحاً.",
        'word_count': "🔢 كم كلمة تريد إنشاؤها؟ (1-1,000,000)",
        'invalid_word_count': "❌ أدخل رقماً بين 1 و 1,000,000.",
        'generated_words': "📚 الكلمات المولدة:",
        'bot_search_prompt': "🤖 أدخل اسم البوت للبحث (بدون @). سأضيف تلقائياً 'bot' إلى النهاية إذا لم يكن موجوداً.\nمثال: mycoolbot أو mycool فقط\n\n(ملاحظة: فحص التوفر محاكى)",
        'bot_search_results': "🤖 نتائج البحث عن البوت '{name}' (محاكاة):",
        'bot_available': "✅ @{name} متاح (محاكاة)!",
        'bot_taken': "❌ @{name} مأخوذ (محاكاة).",
        'invalid_bot_name': "❌ اسم بوت غير صحيح. يجب أن يكون الاسم النهائي (بما في ذلك 'bot') من 5 إلى 32 حرفاً، ويتكون من أحرف وأرقام وشرطات سفلية فقط.",
        'rate_limit_warning': "⚠️ تم الوصول لحد المعدل (محاكاة). توقف لـ {seconds} ثانية...",
        'timeout_error': "⏰ انتهت مهلة الطلب (محاكاة). حاول مرة أخرى.",
        'network_error': "🌐 خطأ في الشبكة (محاكاة). تحقق من اتصالك.",
        'error_occurred': "❌ حدث خطأ: {error}",
        'operation_cancelled': "تم إلغاء العملية. العودة إلى القائمة الرئيسية."
    }
}

# --- Utility Functions ---

def get_text(key: str, lang: str = 'en', **kwargs) -> str:
    """Get translated text with formatting."""
    text = translations.get(lang, translations['en']).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            logger.warning(f"Missing key in translation for '{key}' with kwargs {kwargs}")
            return text
    return text

def get_language(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get user's language preference."""
    return context.user_data.get('language', 'en')

def create_main_keyboard(lang: str = 'en') -> InlineKeyboardMarkup:
    """Create main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton(get_text('generate_username_btn', lang), callback_data='generate_username'),
            InlineKeyboardButton(get_text('generate_word_btn', lang), callback_data='generate_word')
        ],
        [
            InlineKeyboardButton(get_text('bulk_check_btn', lang), callback_data='bulk_check'),
            InlineKeyboardButton(get_text('bot_search_btn', lang), callback_data='bot_search')
        ],
        [
            InlineKeyboardButton(get_text('how_to_btn', lang), callback_data='how_to'),
            InlineKeyboardButton(get_text('language_btn', lang), callback_data='language')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_home_keyboard(lang: str = 'en') -> InlineKeyboardMarkup:
    """Create home button keyboard."""
    keyboard = [[InlineKeyboardButton(get_text('home_btn', lang), callback_data='home')]]
    return InlineKeyboardMarkup(keyboard)

def create_language_keyboard() -> InlineKeyboardMarkup:
    """Create language selection keyboard."""
    keyboard = [
        [
            InlineKeyboardButton(get_text('english_btn', 'en'), callback_data='lang_en'),
            InlineKeyboardButton(get_text('arabic_btn', 'ar'), callback_data='lang_ar')
        ],
        [InlineKeyboardButton(get_text('home_btn', 'en'), callback_data='home')] # Home button always in English for consistency
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Simulated Telegram Username Checker ---

class SimulatedTelegramUsernameChecker:
    """Simulates Telegram username availability checks."""

    def __init__(self):
        # Use the global set of simulated taken usernames
        self.taken_usernames = SIMULATED_TAKEN_USERNAMES

    async def check_username(self, username: str, delay: float = 0.1) -> bool:
        """Simulates checking if a username is available."""
        await asyncio.sleep(delay) # Simulate network delay
        # Check if the username (case-insensitive) is in our simulated taken list
        is_available = username.lower() not in self.taken_usernames
        logger.info(f"Simulated check for '{username}': {'Available' if is_available else 'Taken'}")
        return is_available

    def is_valid_username_format(self, username: str) -> bool:
        """Validate username format (basic check)."""
        if not username or len(username) < MIN_USERNAME_LENGTH or len(username) > MAX_USERNAME_LENGTH:
            return False
        return re.match(r'^[a-zA-Z0-9_]+$', username) is not None

# --- Word Generator ---

class WordGenerator:
    """Generates words in English or Arabic from predefined lists."""

    def __init__(self, language='en'):
        self.language = language

    def generate_words(self, length: Optional[int] = None, count: int = 10, pattern: Optional[str] = None) -> List[str]:
        """Generate words based on specified criteria (length, count, or pattern)."""
        words = []
        if pattern:
            for _ in range(count):
                words.append(self._generate_word_from_pattern(pattern))
        else:
            source_words = list(ARABIC_WORDS) if self.language == 'ar' else list(ENGLISH_WORDS)
            
            if length:
                filtered_words = [w for w in source_words if len(w) == length]
                if filtered_words:
                    words = random.sample(filtered_words, min(count, len(filtered_words)))
                else:
                    # Fallback to random generation if no words match length
                    words = [self._generate_random_word(length) for _ in range(count)]
            else:
                # If no length or pattern, just pick random words
                words = random.sample(source_words, min(count, len(source_words)))
        
        return words[:count]

    def _generate_random_word(self, length: int) -> str:
        """Generate a random word of specified length."""
        if self.language == 'ar':
            chars = 'ابتثجحخدذرزسشصضطظعغفقكلمنهوي'
        else:
            chars = string.ascii_lowercase
        return ''.join(random.choice(chars) for _ in range(length))

    def _generate_word_from_pattern(self, pattern: str) -> str:
        """Generate word from pattern, replacing 'x' with random letters."""
        result = pattern
        # Handle quoted sections (fixed parts)
        quoted_parts = re.findall(r'"([^"]*)"', pattern)
        for quoted in quoted_parts:
            result = result.replace(f'"{quoted}"', quoted)
        
        # Replace x with random letters (not digits for words)
        while PLACEHOLDER_CHAR in result:
            if self.language == 'ar':
                char = random.choice('ابتثجحخدذرزسشصضطظعغفقكلمنهوي')
            else:
                char = random.choice(string.ascii_lowercase)
            result = result.replace(PLACEHOLDER_CHAR, char, 1)
        return result

# --- Telegram Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start command handler."""
    lang = get_language(context)
    await update.message.reply_text(
        get_text('welcome', lang),
        reply_markup=create_main_keyboard(lang)
    )
    return INITIAL_MENU

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer() # Acknowledge the button press
    
    lang = get_language(context)
    
    # Use update.callback_query.message for effective_message in callback queries
    effective_message_for_reply = query.message if query.message else update.effective_message

    if query.data == 'home':
        await effective_message_for_reply.edit_text(
            get_text('welcome', lang),
            reply_markup=create_main_keyboard(lang)
        )
        return INITIAL_MENU
    
    elif query.data == 'generate_username':
        await effective_message_for_reply.edit_text(
            get_text('how_many_names', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_USERNAME_COUNT
    
    elif query.data == 'generate_word':
        await effective_message_for_reply.edit_text(
            get_text('word_length', lang), # Prompt for length or pattern
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_WORD_LENGTH
    
    elif query.data == 'bulk_check':
        await effective_message_for_reply.edit_text(
            get_text('send_bulk_list', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return BULK_LIST
    
    elif query.data == 'bot_search':
        await effective_message_for_reply.edit_text(
            get_text('bot_search_prompt', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_BOT_SEARCH
    
    elif query.data == 'how_to':
        await effective_message_for_reply.edit_text(
            get_text('how_to_text', lang),
            reply_markup=create_home_keyboard(lang),
            parse_mode='Markdown'
        )
        return HOW_TO_INFO
    
    elif query.data == 'language':
        await effective_message_for_reply.edit_text(
            get_text('language_selection', lang),
            reply_markup=create_language_keyboard()
        )
        return SET_LANGUAGE
    
    elif query.data.startswith('lang_'):
        new_lang = query.data.split('_')[1]
        context.user_data['language'] = new_lang
        await effective_message_for_reply.edit_text(
            get_text('language_set', new_lang),
            reply_markup=create_main_keyboard(new_lang)
        )
        return INITIAL_MENU
    
    # --- Download Handlers ---
    elif query.data == 'download_usernames_all':
        await send_download_file(update, context, 'usernames_all')
        return INITIAL_MENU
    elif query.data == 'download_usernames_available':
        await send_download_file(update, context, 'usernames_available')
        return INITIAL_MENU
    elif query.data == 'download_words':
        await send_download_file(update, context, 'words')
        return INITIAL_MENU
    elif query.data == 'download_bulk_all':
        await send_download_file(update, context, 'bulk_all')
        return INITIAL_MENU
    elif query.data == 'download_bulk_available':
        await send_download_file(update, context, 'bulk_available')
        return INITIAL_MENU

    return INITIAL_MENU # Fallback to initial menu if unexpected callback

async def handle_username_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle username count input."""
    lang = get_language(context)
    
    try:
        count = int(update.message.text.strip())
        if 1 <= count <= 500:
            context.user_data['username_count'] = count
            await update.message.reply_text(
                get_text('send_pattern', lang),
                reply_markup=create_home_keyboard(lang)
            )
            return ASK_PATTERN
        else:
            await update.message.reply_text(
                get_text('invalid_number', lang),
                reply_markup=create_home_keyboard(lang)
            )
            return ASK_USERNAME_COUNT
    except ValueError:
        await update.message.reply_text(
            get_text('invalid_number', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_USERNAME_COUNT

async def handle_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle pattern input."""
    lang = get_language(context)
    pattern = update.message.text.strip()
    
    # Basic validation for pattern
    if not pattern or (PLACEHOLDER_CHAR not in pattern and '"' not in pattern):
        await update.message.reply_text(
            get_text('invalid_pattern', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_PATTERN
    
    context.user_data['pattern'] = pattern
    await update.message.reply_text(
        get_text('ask_delay', lang),
        reply_markup=create_home_keyboard(lang)
    )
    return ASK_DELAY

async def handle_delay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle delay input and start username generation."""
    lang = get_language(context)
    
    try:
        delay = float(update.message.text.strip())
        if delay >= 0:
            context.user_data['delay'] = delay
            
            count = context.user_data['username_count']
            pattern = context.user_data['pattern']
            
            status_msg = await update.message.reply_text(
                get_text('searching_names', lang, count=count, pattern=pattern),
                reply_markup=create_home_keyboard(lang)
            )
            
            all_generated_usernames = [] # Store all generated for download
            available_usernames = [] # Store only available for display and download
            
            checker = SimulatedTelegramUsernameChecker()
            
            checked_count = 0
            taken_count = 0

            for i in range(count):
                username = generate_username_from_pattern(pattern)
                all_generated_usernames.append(username) # Add to all generated list
                
                if not (MIN_USERNAME_LENGTH <= len(username) <= MAX_USERNAME_LENGTH):
                    continue # Skip invalid length usernames
                
                try:
                    is_available = await checker.check_username(username, delay)
                    checked_count += 1
                    
                    if is_available:
                        available_usernames.append(username)
                    else:
                        taken_count += 1
                    
                    if checked_count % 10 == 0 or checked_count == count:
                        current_results_display = ""
                        if available_usernames:
                            current_results_display = f"\n\n✅ {get_text('available_usernames', lang)}\n"
                            for uname in available_usernames[-5:]:
                                current_results_display += f"@{uname}\n"
                            if len(available_usernames) > 5:
                                current_results_display += "...\n"
                        
                        progress_text = get_text('checking_progress', lang,
                            current_checked=checked_count,
                            total_to_check=count,
                            available_count=len(available_usernames),
                            taken_count=taken_count,
                            remaining_count=count - checked_count
                        ) + current_results_display
                        
                        try:
                            await status_msg.edit_text(
                                progress_text,
                                reply_markup=create_home_keyboard(lang)
                            )
                        except TelegramError as e:
                            if "Message is not modified" not in str(e):
                                logger.warning(f"Could not edit message: {e}")
                    
                    await asyncio.sleep(delay)
                        
                except Exception as e:
                    logger.error(f"Error during simulated username check for {username}: {e}")
                    continue
            
            # Store results in user_data for download
            context.user_data['last_generated_usernames_all'] = all_generated_usernames
            context.user_data['last_generated_usernames_available'] = available_usernames

            # Create download buttons
            download_keyboard_buttons = []
            if all_generated_usernames:
                download_keyboard_buttons.append(InlineKeyboardButton(get_text('download_all_usernames_btn', lang), callback_data='download_usernames_all'))
            if available_usernames:
                download_keyboard_buttons.append(InlineKeyboardButton(get_text('download_available_usernames_btn', lang), callback_data='download_usernames_available'))
            
            final_keyboard = InlineKeyboardMarkup([download_keyboard_buttons, [InlineKeyboardButton(get_text('home_btn', lang), callback_data='home')]]) if download_keyboard_buttons else create_main_keyboard(lang)

            if available_usernames:
                result_text = f"{get_text('available_usernames', lang)}\n\n"
                for username in available_usernames[:20]:
                    result_text += f"@{username}\n"
                
                if len(available_usernames) > 20:
                    result_text += f"\n... {len(available_usernames) - 20} {get_text('more_available', lang) if lang == 'en' else 'أخرى متاحة'}!"
            else:
                result_text = get_text('no_available', lang)
            
            await status_msg.edit_text(
                result_text,
                reply_markup=final_keyboard
            )
            
            return INITIAL_MENU
        else:
            await update.message.reply_text(
                get_text('invalid_delay', lang),
                reply_markup=create_home_keyboard(lang)
            )
            return ASK_DELAY
    except ValueError:
        await update.message.reply_text(
            get_text('invalid_delay', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_DELAY
    except Exception as e:
        logger.error(f"Error in handle_delay: {e}")
        await update.message.reply_text(
            get_text('error_occurred', lang, error=str(e)),
            reply_markup=create_main_keyboard(lang)
        )
        return INITIAL_MENU

def generate_username_from_pattern(pattern: str) -> str:
    """Generate username from pattern, handling quoted parts and 'x' placeholders."""
    result = pattern
    
    # Extract and replace quoted sections first (fixed parts)
    # This ensures "myname" in "myname_x_x" remains "myname"
    parts = []
    last_idx = 0
    for match in re.finditer(r'"([^"]*)"', pattern):
        # Add text before the quote
        parts.append(pattern[last_idx:match.start()])
        # Add the quoted text itself
        parts.append(match.group(1))
        last_idx = match.end()
    parts.append(pattern[last_idx:]) # Add remaining text

    processed_pattern = "".join(parts)

    # Replace 'x' with random characters/digits
    final_username = []
    for char in processed_pattern:
        if char == PLACEHOLDER_CHAR:
            final_username.append(random.choice(string.ascii_lowercase + string.digits))
        else:
            final_username.append(char)
    
    return "".join(final_username)

async def handle_word_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle word pattern or length input."""
    lang = get_language(context)
    text = update.message.text.strip()
    
    # Check if it's a pattern with 'x' or quoted parts
    if PLACEHOLDER_CHAR in text or '"' in text:
        context.user_data['word_pattern'] = text
        context.user_data['word_length'] = None # Clear previous length
        await update.message.reply_text(
            get_text('word_count', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_WORD_COUNT
    else:
        # Try to parse as length
        try:
            length = int(text)
            if 3 <= length <= 15:
                context.user_data['word_length'] = length
                context.user_data['word_pattern'] = None # Clear previous pattern
                await update.message.reply_text(
                    get_text('word_count', lang),
                    reply_markup=create_home_keyboard(lang)
                )
                return ASK_WORD_COUNT
            else:
                await update.message.reply_text(
                    get_text('invalid_word_length', lang),
                    reply_markup=create_home_keyboard(lang)
                )
                return ASK_WORD_LENGTH
        except ValueError:
            await update.message.reply_text(
                get_text('invalid_word_length', lang),
                reply_markup=create_home_keyboard(lang)
            )
            return ASK_WORD_LENGTH

async def handle_word_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle word count input and generate words."""
    lang = get_language(context)
    
    try:
        # Increased limit to 1,000,000
        count = int(update.message.text.strip())
        if 1 <= count <= 1_000_000: # Updated limit
            length = context.user_data.get('word_length')
            pattern = context.user_data.get('word_pattern')
            
            generator = WordGenerator(lang)
            words = generator.generate_words(length=length, count=count, pattern=pattern)
            
            context.user_data['last_generated_words'] = words # Store for download

            download_keyboard_buttons = []
            if words:
                download_keyboard_buttons.append(InlineKeyboardButton(get_text('download_words_btn', lang), callback_data='download_words'))
            
            final_keyboard = InlineKeyboardMarkup([download_keyboard_buttons, [InlineKeyboardButton(get_text('home_btn', lang), callback_data='home')]]) if download_keyboard_buttons else create_main_keyboard(lang)

            if words:
                result_text = f"{get_text('generated_words', lang)}\n\n"
                # Display words in chunks if too many for a single message
                display_limit = 50 # Max words to show directly
                for word in words[:display_limit]:
                    result_text += f"• {word}\n"
                
                if len(words) > display_limit:
                    result_text += f"\n... {len(words) - display_limit} {get_text('more_words_generated', lang) if lang == 'en' else 'كلمات أخرى تم توليدها'}!"
            else:
                result_text = get_text('no_available', lang) # Re-using no_available text
            
            await update.message.reply_text(
                result_text,
                reply_markup=final_keyboard
            )
            return INITIAL_MENU
        else:
            await update.message.reply_text(
                get_text('invalid_word_count', lang),
                reply_markup=create_home_keyboard(lang)
            )
            return ASK_WORD_COUNT
    except ValueError:
        await update.message.reply_text(
            get_text('invalid_word_count', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_WORD_COUNT
    except Exception as e:
        logger.error(f"Error in handle_word_count: {e}")
        await update.message.reply_text(
            get_text('error_occurred', lang, error=str(e)),
            reply_markup=create_main_keyboard(lang)
        )
        return INITIAL_MENU

async def _perform_bulk_check(update: Update, context: ContextTypes.DEFAULT_TYPE, usernames_to_check: List[str]) -> int:
    """Helper function to perform the actual bulk check logic."""
    lang = get_language(context)
    
    if not usernames_to_check or len(usernames_to_check) > 500: # Still limit to 500 for processing efficiency
        await update.effective_message.reply_text(
            get_text('invalid_bulk_list', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return BULK_LIST
    
    delay = context.user_data.get('delay', 0.1)

    status_msg = await update.effective_message.reply_text(
        get_text('bulk_checking', lang, count=len(usernames_to_check)),
        reply_markup=create_home_keyboard(lang)
    )
    
    checked_results = [] # Store {username, is_available} for download
    available_usernames = []
    checked_count = 0
    taken_count = 0
    
    checker = SimulatedTelegramUsernameChecker()

    for username in usernames_to_check:
        try:
            is_available = await checker.check_username(username, delay)
            checked_count += 1
            
            checked_results.append({'username': username, 'is_available': is_available})

            if is_available:
                available_usernames.append(username)
            else:
                taken_count += 1
            
            if checked_count % 10 == 0 or checked_count == len(usernames_to_check):
                progress_text = get_text('checking_progress', lang,
                    current_checked=checked_count,
                    total_to_check=len(usernames_to_check),
                    available_count=len(available_usernames),
                    taken_count=taken_count,
                    remaining_count=len(usernames_to_check) - checked_count
                )
                
                try:
                    await status_msg.edit_text(
                        progress_text,
                        reply_markup=create_home_keyboard(lang)
                    )
                except TelegramError as e:
                    if "Message is not modified" not in str(e):
                        logger.warning(f"Could not edit message during bulk check: {e}")
                
            await asyncio.sleep(delay)
                
        except Exception as e:
            logger.error(f"Error during simulated bulk check for {username}: {e}")
            continue
    
    context.user_data['last_bulk_checked_all'] = checked_results
    context.user_data['last_bulk_checked_available'] = available_usernames

    download_keyboard_buttons = []
    if checked_results:
        download_keyboard_buttons.append(InlineKeyboardButton(get_text('download_bulk_all_btn', lang), callback_data='download_bulk_all'))
    if available_usernames:
        download_keyboard_buttons.append(InlineKeyboardButton(get_text('download_bulk_available_btn', lang), callback_data='download_bulk_available'))

    final_keyboard = InlineKeyboardMarkup([download_keyboard_buttons, [InlineKeyboardButton(get_text('home_btn', lang), callback_data='home')]]) if download_keyboard_buttons else create_main_keyboard(lang)

    if available_usernames:
        result_text = f"{get_text('available_usernames', lang)}\n\n"
        for username in available_usernames[:30]:
            result_text += f"@{username}\n"
        
        if len(available_usernames) > 30:
            result_text += f"\n... {len(available_usernames) - 30} {get_text('more_available', lang) if lang == 'en' else 'أخرى متاحة'}!"
    else:
        result_text = get_text('no_available', lang)
    
    await status_msg.edit_text(
        result_text,
        reply_markup=final_keyboard
    )
    
    return INITIAL_MENU

async def handle_bulk_list_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bulk username list sent as plain text."""
    text = update.message.text.strip()
    usernames = [line.strip().replace('@', '') for line in text.split('\n') if line.strip()]
    
    checker = SimulatedTelegramUsernameChecker()
    valid_usernames = [u for u in usernames if checker.is_valid_username_format(u)]

    return await _perform_bulk_check(update, context, valid_usernames)

async def handle_bulk_list_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bulk username list sent as a .txt file."""
    lang = get_language(context)
    document = update.message.document

    # Check if a document is actually present and has a file name
    if not document or not document.file_name:
        await update.message.reply_text(
            get_text('invalid_bulk_list', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return BULK_LIST

    if not document.file_name.lower().endswith('.txt'):
        await update.message.reply_text(
            get_text('invalid_bulk_list', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return BULK_LIST

    try:
        file_id = document.file_id
        file_object = await context.bot.get_file(file_id)
        
        # Create a temporary file path
        temp_file_path = tempfile.mktemp(suffix='.txt')

        # Download the file to the temporary path using download_to_drive
        await file_object.download_to_drive(temp_file_path)

        # Read content from the temporary file
        with open(temp_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            file_content = f.read()
        
        # Clean up the temporary file
        os.remove(temp_file_path)

        usernames = [line.strip().replace('@', '') for line in file_content.split('\n') if line.strip()]
        
        checker = SimulatedTelegramUsernameChecker()
        valid_usernames = [u for u in usernames if checker.is_valid_username_format(u)]

        return await _perform_bulk_check(update, context, valid_usernames)

    except Exception as e:
        logger.error(f"Error handling bulk file upload: {e}", exc_info=True)
        await update.message.reply_text(
            get_text('error_occurred', lang, error="Failed to process file."),
            reply_markup=create_home_keyboard(lang)
        )
        return BULK_LIST


async def handle_bot_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bot username search."""
    lang = get_language(context)
    user_input = update.message.text.strip().replace('@', '').lower()
    
    # Auto-add 'bot' suffix if not present
    bot_name_to_check = user_input
    if not bot_name_to_check.endswith('bot'):
        bot_name_to_check += 'bot'
    
    checker = SimulatedTelegramUsernameChecker()
    
    # Validate the final formatted bot name
    if not checker.is_valid_username_format(bot_name_to_check):
        await update.message.reply_text(
            get_text('invalid_bot_name', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_BOT_SEARCH
    
    status_msg = await update.message.reply_text(
        get_text('bot_search_results', lang, name=bot_name_to_check),
        reply_markup=create_home_keyboard(lang)
    )
    
    try:
        # Use the general check_username for bot names after formatting
        is_available = await checker.check_username(bot_name_to_check, delay=0.5) # Small delay for bot search
        
        if is_available:
            result_text = get_text('bot_available', lang, name=bot_name_to_check)
        else:
            result_text = get_text('bot_taken', lang, name=bot_name_to_check)
        
        await status_msg.edit_text(
            f"{get_text('bot_search_results', lang, name=bot_name_to_check)}\n\n{result_text}",
            reply_markup=create_main_keyboard(lang)
        )
        
    except Exception as e:
        logger.error(f"Error during simulated bot check for {bot_name_to_check}: {e}")
        await status_msg.edit_text(
            get_text('error_occurred', lang, error=str(e)),
            reply_markup=create_main_keyboard(lang)
        )
    
    return INITIAL_MENU

async def send_download_file(update: Update, context: ContextTypes.DEFAULT_TYPE, data_type: str) -> None:
    """Sends the requested data as a text file."""
    lang = get_language(context)
    file_content = ""
    file_name = ""

    # Determine the effective chat and message for replies/sends
    # This logic is now robust for both Message and CallbackQuery updates
    chat_id_for_send = update.effective_chat.id
    message_for_reply = update.effective_message

    if not chat_id_for_send or not message_for_reply:
        logger.error("Could not determine effective chat or message for sending download file.")
        return # Cannot proceed without a valid chat/message to reply to

    if data_type == 'usernames_all':
        data = context.user_data.get('last_generated_usernames_all')
        if data:
            file_content = "\n".join([f"@{u}" for u in data])
            file_name = "generated_usernames_all.txt"
    elif data_type == 'usernames_available':
        data = context.user_data.get('last_generated_usernames_available')
        if data:
            file_content = "\n".join([f"@{u}" for u in data])
            file_name = "generated_usernames_available.txt"
    elif data_type == 'words':
        data = context.user_data.get('last_generated_words')
        if data:
            file_content = "\n".join(data)
            file_name = "generated_words.txt"
    elif data_type == 'bulk_all':
        data = context.user_data.get('last_bulk_checked_all')
        if data:
            file_content = "\n".join([f"@{item['username']} ({get_text('available', lang) if item['is_available'] else get_text('taken', lang)})" for item in data])
            file_name = "bulk_checked_usernames_all.txt"
    elif data_type == 'bulk_available':
        data = context.user_data.get('last_bulk_checked_available')
        if data:
            file_content = "\n".join([f"@{u}" for u in data])
            file_name = "bulk_checked_usernames_available.txt"
    
    if file_content and file_name:
        try:
            # Create a temporary file
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8', suffix='.txt') as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            
            # Send the file
            with open(temp_file_path, 'rb') as f:
                await context.bot.send_document(chat_id=chat_id_for_send, document=InputFile(f, filename=file_name))
            
            await message_for_reply.reply_text(get_text('file_sent', lang), reply_markup=create_main_keyboard(lang))

        except Exception as e:
            logger.error(f"Error sending file: {e}", exc_info=True)
            await message_for_reply.reply_text(get_text('error_occurred', lang, error=str(e)), reply_markup=create_main_keyboard(lang))
        finally:
            # Clean up the temporary file
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    else:
        await message_for_reply.reply_text(get_text('no_data_to_download', lang), reply_markup=create_main_keyboard(lang))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation."""
    lang = get_language(context)
    # Use update.effective_message for replies in cancel handler
    if update.effective_message:
        await update.effective_message.reply_text(
            get_text('operation_cancelled', lang),
            reply_markup=create_main_keyboard(lang)
        )
    return INITIAL_MENU

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    
    # Attempt to send a generic error message to the user
    # Determine the effective message to reply to
    effective_message_for_reply = None
    if isinstance(update, Update):
        if update.effective_message:
            effective_message_for_reply = update.effective_message
        elif update.callback_query and update.callback_query.message:
            effective_message_for_reply = update.callback_query.message

    if effective_message_for_reply:
        lang = get_language(context)
        error_message = get_text('error_occurred', lang, error="Please try again or contact support.")
        try:
            await effective_message_for_reply.reply_text(
                error_message,
                reply_markup=create_main_keyboard(lang)
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")

def main():
    """Start the bot."""
    # Ensure TOKEN, WEBHOOK_URL are set before building the application
    if not TOKEN:
        logger.error("Bot token is not set! Please set TELEGRAM_TOKEN environment variable.")
        print("\nERROR: Bot token is not set! Please set TELEGRAM_TOKEN environment variable.")
        print("You can get a token from @BotFather on Telegram by sending /newbot.")
        return
    
    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL is not set! Please set WEBHOOK_URL environment variable.")
        print("\nERROR: WEBHOOK_URL is not set! Please set WEBHOOK_URL environment variable.")
        print("This should be the public URL of your deployed application (e.g., from Railway).")
        return
    
    if ADMIN_ID is None:
        print("\nWARNING: ADMIN_ID environment variable is not set or is invalid. Admin features (if any) will be unavailable.")


    application = ApplicationBuilder().token(TOKEN).build()
    
    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            INITIAL_MENU: [
                CallbackQueryHandler(button_handler),
                # Add download button handlers to INITIAL_MENU state
                CallbackQueryHandler(button_handler, pattern='^download_usernames_all$'),
                CallbackQueryHandler(button_handler, pattern='^download_usernames_available$'),
                CallbackQueryHandler(button_handler, pattern='^download_words$'),
                CallbackQueryHandler(button_handler, pattern='^download_bulk_all$'),
                CallbackQueryHandler(button_handler, pattern='^download_bulk_available$'),
            ],
            ASK_USERNAME_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username_count),
                CallbackQueryHandler(button_handler, pattern='^home$') # Allow going home from here
            ],
            ASK_PATTERN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pattern),
                CallbackQueryHandler(button_handler, pattern='^home$')
            ],
            ASK_DELAY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delay),
                CallbackQueryHandler(button_handler, pattern='^home$')
            ],
            ASK_WORD_LENGTH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_word_length),
                CallbackQueryHandler(button_handler, pattern='^home$')
            ],
            ASK_WORD_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_word_count),
                CallbackQueryHandler(button_handler, pattern='^home$')
            ],
            BULK_LIST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bulk_list_text), # Handles text input
                MessageHandler(filters.Document.ALL, handle_bulk_list_file), # Handles any document, then check .txt inside
                CallbackQueryHandler(button_handler, pattern='^home$')
            ],
            ASK_BOT_SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bot_search),
                CallbackQueryHandler(button_handler, pattern='^home$')
            ],
            HOW_TO_INFO: [CallbackQueryHandler(button_handler, pattern='^home$')],
            SET_LANGUAGE: [CallbackQueryHandler(button_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel), CallbackQueryHandler(cancel, pattern='^home$')],
        per_message=False # Process updates per conversation, not per message
    )
    
    # Add handlers
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    # Start the bot with webhook
    logger.info("Starting RipperTek Telegram Bot with Webhook...")
    application.run_webhook(
        listen="0.0.0.0", # Listen on all available network interfaces
        port=PORT,
        url_path=TOKEN, # Use the token as the path for security
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == '__main__':
    main()

