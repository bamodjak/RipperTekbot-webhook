import logging
import os
import random
import string
import asyncio
import warnings
import re
import httpx
from typing import List, Dict, Set, Optional

# Setup logging first
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Import English words with proper error handling
try:
    from english_words import get_english_words_set
    ENGLISH_WORDS = get_english_words_set(['web2'], lower=True)
    logger.info(f"Loaded {len(ENGLISH_WORDS)} English words")
except ImportError:
    logger.warning("english_words library not found. Using fallback words.")
    ENGLISH_WORDS = set()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning, module="telegram.ext.conversationhandler")

# Load Telegram token
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN environment variable not set!")

# States for ConversationHandler
(INITIAL_MENU, ASK_USERNAME_COUNT, ASK_PATTERN, ASK_DELAY, BULK_LIST,
 HOW_TO_INFO, SET_LANGUAGE, ASK_WORD_LENGTH, ASK_WORD_COUNT, 
 SHOW_WORD_RESULTS, ASK_BOT_SEARCH) = range(11)

# Arabic words dataset
ARABIC_WORDS = {
    'كتاب', 'مدرسة', 'بيت', 'قلم', 'ورقة', 'طالب', 'معلم', 'درس', 'امتحان', 'نجاح',
    'حب', 'سلام', 'أمل', 'نور', 'حياة', 'عمل', 'وقت', 'يوم', 'ليلة', 'صباح',
    'مساء', 'شمس', 'قمر', 'نجم', 'بحر', 'جبل', 'شجرة', 'زهرة', 'طائر', 'سمك',
    'طعام', 'ماء', 'خبز', 'لحم', 'فاكهة', 'خضار', 'لبن', 'شاي', 'قهوة', 'عصير',
    'أب', 'أم', 'ابن', 'ابنة', 'أخ', 'أخت', 'جد', 'جدة', 'عم', 'خال',
    'صديق', 'جار', 'ضيف', 'طبيب', 'مهندس', 'معلم', 'طالب', 'عامل', 'تاجر', 'فلاح'
}

# Constants
MIN_USERNAME_LENGTH = 5
MAX_USERNAME_LENGTH = 32
PLACEHOLDER_CHAR = 'x'

# Fallback words for generation
FALLBACK_WORDS_EN = [
    "user", "admin", "tech", "pro", "game", "bot", "tool", "alpha", "beta",
    "master", "geek", "coder", "dev", "creator", "digital", "online", "system",
    "prime", "expert", "fusion", "galaxy", "infinity", "legend", "nova", "omega",
    "phantom", "quest", "rocket", "spirit", "ultra", "vision", "wizard", "zenith"
]

FALLBACK_WORDS_AR = [
    "مستخدم", "مسؤول", "تقنية", "محترف", "لعبة", "بوت", "أداة", "مبدع", "رقمي",
    "خبير", "عالم", "نظام", "أفق", "نجم", "بوابة", "روح", "قوة", "فارس", "بطل"
]

# Translations
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
        'ask_delay': "⏱️ Enter delay between checks (seconds):\n• 0.1 = 100ms\n• 1.0 = 1 second\n• 0 = no delay",
        'invalid_delay': "❌ Please enter a valid delay (e.g., 0.1, 1, 5).",
        'searching_names': "🔍 Searching for {count} usernames with pattern '{pattern}'...",
        'checking_progress': "⏳ Progress: {current_checked}/{total_to_check}\n✅ Available: {available_count}\n❌ Taken: {taken_count}\n\n📊 Remaining: {remaining_count}",
        'check_complete': "✅ Check Complete!\n\n📊 Results:\n• Total checked: {total_checked}\n• Available: {available_count}\n• Taken: {taken_count}",
        'available_usernames': "✅ Available Usernames:",
        'no_available': "❌ No available usernames found.",
        'send_bulk_list': "📄 Send your list of usernames (one per line, max 500):",
        'invalid_bulk_list': "❌ Invalid list. Please send usernames (one per line, max 500).",
        'bulk_checking': "🔍 Checking {count} usernames from your list...",
        'how_to_text': """📖 **How to Use RipperTek Bot**

🔤 **Username Generator:**
• Choose how many to generate (1-500)
• Create patterns with 'x' for random chars
• Set delay between checks
• Get available usernames instantly

📚 **Word Generator:**
• Generate English or Arabic words
• Choose word length and count
• Perfect for creative projects

📄 **Bulk Check:**
• Send a list of usernames
• Check availability in bulk
• Get detailed results

🤖 **Bot Search:**
• Search for bot usernames
• Uses @botname pattern
• Find available bot names

💡 **Tips:**
• Use quotes in patterns for fixed text
• Shorter delays = faster but may hit limits
• Bot names must end with 'bot'""",
        'word_length': "📏 Enter desired word length (3-15 characters):",
        'invalid_word_length': "❌ Please enter a length between 3 and 15.",
        'word_count': "🔢 How many words to generate? (1-1000)",
        'invalid_word_count': "❌ Please enter a number between 1 and 1000.",
        'word_pattern': "📝 Send a word pattern (e.g., `app_x_x_x` where 'x' = random letters):\n\n💡 Tips:\n• Use quotes for fixed parts: `\"my\"_x_x`\n• x = random letter\n• Or just enter word length (3-15)",
        'invalid_word_pattern': "❌ Invalid pattern. Use 'x' for random letters or enter a number (3-15).",
        'generated_words': "📚 Generated Words:",
        'bot_search_prompt': "🤖 Enter bot name to search (without @):\nExample: mybotname",
        'bot_search_results': "🤖 Bot Search Results for '{name}':",
        'bot_available': "✅ @{name} is available!",
        'bot_taken': "❌ @{name} is taken.",
        'invalid_bot_name': "❌ Invalid bot name. Must be 5-32 characters, alphanumeric + underscores only.",
        'rate_limit_warning': "⚠️ Rate limit reached. Pausing for {seconds} seconds...",
        'timeout_error': "⏰ Request timed out. Please try again.",
        'network_error': "🌐 Network error. Please check your connection.",
        'error_occurred': "❌ An error occurred: {error}"
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
        'ask_delay': "⏱️ أدخل التأخير بين الفحوصات (ثواني):\n• 0.1 = 100 ميلي ثانية\n• 1.0 = ثانية واحدة\n• 0 = بدون تأخير",
        'invalid_delay': "❌ أدخل تأخيراً صحيحاً (مثال: 0.1، 1، 5).",
        'searching_names': "🔍 البحث عن {count} أسماء مستخدمين بالنمط '{pattern}'...",
        'checking_progress': "⏳ التقدم: {current_checked}/{total_to_check}\n✅ متاح: {available_count}\n❌ مأخوذ: {taken_count}\n\n📊 المتبقي: {remaining_count}",
        'check_complete': "✅ اكتمل الفحص!\n\n📊 النتائج:\n• إجمالي المفحوص: {total_checked}\n• متاح: {available_count}\n• مأخوذ: {taken_count}",
        'available_usernames': "✅ أسماء المستخدمين المتاحة:",
        'no_available': "❌ لم يتم العثور على أسماء مستخدمين متاحة.",
        'send_bulk_list': "📄 أرسل قائمتك من أسماء المستخدمين (واحد في كل سطر، أقصى 500):",
        'invalid_bulk_list': "❌ قائمة غير صحيحة. أرسل أسماء مستخدمين (واحد في كل سطر، أقصى 500).",
        'bulk_checking': "🔍 فحص {count} أسماء مستخدمين من قائمتك...",
        'how_to_text': """📖 **كيفية استخدام بوت RipperTek**

🔤 **منشئ أسماء المستخدمين:**
• اختر كم تريد إنشاؤه (1-500)
• أنشئ أنماط بـ 'x' للحروف العشوائية
• حدد التأخير بين الفحوصات
• احصل على أسماء مستخدمين متاحة فوراً

📚 **منشئ الكلمات:**
• أنشئ كلمات إنجليزية أو عربية
• اختر طول الكلمة والعدد
• مثالي للمشاريع الإبداعية

📄 **الفحص المجمع:**
• أرسل قائمة أسماء مستخدمين
• فحص التوفر بالجملة
• احصل على نتائج مفصلة

🤖 **البحث عن البوت:**
• ابحث عن أسماء البوت
• يستخدم نمط @botname
• اعثر على أسماء بوت متاحة

💡 **نصائح:**
• استخدم الاقتباس في الأنماط للنص الثابت
• التأخيرات الأقصر = أسرع لكن قد تصل للحدود
• أسماء البوت يجب أن تنتهي بـ 'bot'""",
        'word_length': "📏 أدخل طول الكلمة المطلوب (3-15 حرف):",
        'invalid_word_length': "❌ أدخل طولاً بين 3 و 15.",
        'word_count': "🔢 كم كلمة تريد إنشاؤها؟ (1-1000)",
        'invalid_word_count': "❌ أدخل رقماً بين 1 و 1000.",
        'word_pattern': "📝 أرسل نمط كلمة (مثال: `app_x_x_x` حيث 'x' = حروف عشوائية):\n\n💡 نصائح:\n• استخدم الاقتباس للأجزاء الثابتة: `\"اسمي\"_x_x`\n• x = حرف عشوائي\n• أو أدخل طول الكلمة فقط (3-15)",
        'invalid_word_pattern': "❌ نمط غير صحيح. استخدم 'x' للحروف العشوائية أو أدخل رقماً (3-15).",
        'generated_words': "📚 الكلمات المولدة:",
        'bot_search_prompt': "🤖 أدخل اسم البوت للبحث (بدون @):\nمثال: mybotname",
        'bot_search_results': "🤖 نتائج البحث عن البوت '{name}':",
        'bot_available': "✅ @{name} متاح!",
        'bot_taken': "❌ @{name} مأخوذ.",
        'invalid_bot_name': "❌ اسم بوت غير صحيح. يجب أن يكون 5-32 حرف، أحرف وأرقام + شرطات سفلية فقط.",
        'rate_limit_warning': "⚠️ تم الوصول لحد المعدل. توقف لـ {seconds} ثانية...",
        'timeout_error': "⏰ انتهت مهلة الطلب. حاول مرة أخرى.",
        'network_error': "🌐 خطأ في الشبكة. تحقق من اتصالك.",
        'error_occurred': "❌ حدث خطأ: {error}"
    }
}

class TelegramUsernameChecker:
    """Enhanced username checker with accurate availability detection."""
    
    def __init__(self):
        self.session = None
        self.rate_limit_delay = 0.1
        self.max_retries = 3
        
    async def __aenter__(self):
        self.session = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()
    
    async def check_username(self, username: str) -> bool:
        """Check if username is available. Returns True if available, False if taken."""
        if not self.is_valid_username(username):
            return False
            
        for attempt in range(self.max_retries):
            try:
                # More accurate method using Telegram's web interface
                response = await self.session.get(
                    f"https://t.me/{username}",
                    follow_redirects=True
                )
                
                if response.status_code == 200:
                    content = response.text.lower()
                    # Check for specific indicators that username is taken
                    taken_indicators = [
                        'tgme_page_title',
                        'tgme_page_description', 
                        'class="tgme_page"',
                        'tg://resolve',
                        'channel_title',
                        'chat_title'
                    ]
                    
                    if any(indicator in content for indicator in taken_indicators):
                        return False  # Username is taken
                    
                    # Check if it shows "User not found" or similar
                    if 'user not found' in content or 'not found' in content:
                        return True  # Username is available
                        
                elif response.status_code == 404:
                    return True  # Username is available
                
                # Additional check using different endpoint
                check_response = await self.session.get(
                    f"https://telegram.me/{username}",
                    follow_redirects=False
                )
                
                if check_response.status_code == 404:
                    return True
                elif check_response.status_code == 302:
                    location = check_response.headers.get('location', '')
                    if 'tg://resolve' in location or 't.me' in location:
                        return False
                
                # Default to taken for safety
                return False
                
            except httpx.TimeoutException:
                logger.warning(f"Timeout checking {username}, attempt {attempt + 1}")
                if attempt == self.max_retries - 1:
                    return False
                await asyncio.sleep(1.0)
                
            except Exception as e:
                logger.error(f"Error checking username {username}: {e}")
                if attempt == self.max_retries - 1:
                    return False
                await asyncio.sleep(1.0)
        
        return False
    
    async def check_bot_username(self, botname: str) -> bool:
        """Specifically check bot usernames with bot suffix."""
        if not botname.lower().endswith('bot'):
            botname += 'bot'
            
        return await self.check_username(botname)
    
    def is_valid_username(self, username: str) -> bool:
        """Validate username format."""
        if not username or len(username) < 5 or len(username) > 32:
            return False
        return re.match(r'^[a-zA-Z0-9_]+$', username) is not None

class WordGenerator:
    """Enhanced word generator with better language support."""
    
    def __init__(self, language='en'):
        self.language = language
        
    def generate_words(self, length: int = None, count: int = 10) -> List[str]:
        """Generate words based on specified criteria."""
        try:
            if self.language == 'ar':
                return self._generate_arabic_words(length, count)
            else:
                return self._generate_english_words(length, count)
        except Exception as e:
            logger.error(f"Error generating words: {e}")
            return []
    
    def _generate_english_words(self, length: int = None, count: int = 10) -> List[str]:
        """Generate English words."""
        words = []
        
        if ENGLISH_WORDS:
            # Use real English words
            word_list = list(ENGLISH_WORDS)
            if length:
                word_list = [w for w in word_list if len(w) == length]
            
            if word_list:
                words = random.sample(word_list, min(count, len(word_list)))
            else:
                # Fallback if no words match length
                words = self._generate_fallback_words('en', length, count)
        else:
            # Use fallback words
            words = self._generate_fallback_words('en', length, count)
        
        return words[:count]
    
    def _generate_arabic_words(self, length: int = None, count: int = 10) -> List[str]:
        """Generate Arabic words."""
        word_list = list(ARABIC_WORDS)
        
        if length:
            word_list = [w for w in word_list if len(w) == length]
        
        if word_list:
            return random.sample(word_list, min(count, len(word_list)))
        else:
            # Generate from fallback
            return self._generate_fallback_words('ar', length, count)
    
    def _generate_fallback_words(self, lang: str, length: int = None, count: int = 10) -> List[str]:
        """Generate fallback words when no suitable words are found."""
        fallback = FALLBACK_WORDS_AR if lang == 'ar' else FALLBACK_WORDS_EN
        
        if length:
            filtered = [w for w in fallback if len(w) == length]
            if filtered:
                return random.sample(filtered, min(count, len(filtered)))
            else:
                # Generate random words of specified length
                return [self._generate_random_word(length, lang) for _ in range(count)]
        
        return random.sample(fallback, min(count, len(fallback)))
    
    def _generate_random_word(self, length: int, lang: str) -> str:
        """Generate a random word of specified length."""
        if lang == 'ar':
            chars = 'ابتثجحخدذرزسشصضطظعغفقكلمنهوي'
        else:
            chars = string.ascii_lowercase
        
        return ''.join(random.choice(chars) for _ in range(length))

def get_text(key: str, lang: str = 'en', **kwargs) -> str:
    """Get translated text with formatting."""
    text = translations.get(lang, translations['en']).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
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
        [InlineKeyboardButton(get_text('home_btn', 'en'), callback_data='home')]
    ]
    return InlineKeyboardMarkup(keyboard)

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
    await query.answer()
    
    lang = get_language(context)
    
    if query.data == 'home':
        await query.edit_message_text(
            get_text('welcome', lang),
            reply_markup=create_main_keyboard(lang)
        )
        return INITIAL_MENU
    
    elif query.data == 'generate_username':
        await query.edit_message_text(
            get_text('how_many_names', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_USERNAME_COUNT
    
    elif query.data == 'generate_word':
        await query.edit_message_text(
            get_text('word_pattern', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_WORD_LENGTH
    
    elif query.data == 'bulk_check':
        await query.edit_message_text(
            get_text('send_bulk_list', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return BULK_LIST
    
    elif query.data == 'bot_search':
        await query.edit_message_text(
            get_text('bot_search_prompt', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_BOT_SEARCH
    
    elif query.data == 'how_to':
        await query.edit_message_text(
            get_text('how_to_text', lang),
            reply_markup=create_home_keyboard(lang),
            parse_mode='Markdown'
        )
        return HOW_TO_INFO
    
    elif query.data == 'language':
        await query.edit_message_text(
            get_text('language_selection', lang),
            reply_markup=create_language_keyboard()
        )
        return SET_LANGUAGE
    
    elif query.data.startswith('lang_'):
        new_lang = query.data.split('_')[1]
        context.user_data['language'] = new_lang
        await query.edit_message_text(
            get_text('language_set', new_lang),
            reply_markup=create_main_keyboard(new_lang)
        )
        return INITIAL_MENU
    
    return INITIAL_MENU

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
    
    if pattern and PLACEHOLDER_CHAR in pattern:
        context.user_data['pattern'] = pattern
        await update.message.reply_text(
            get_text('ask_delay', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_DELAY
    else:
        await update.message.reply_text(
            get_text('invalid_pattern', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_PATTERN

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
            
            available_usernames = await generate_usernames_with_progress(
                pattern, count, delay, status_msg, lang
            )
            
            if available_usernames:
                result_text = f"{get_text('available_usernames', lang)}\n\n"
                for username in available_usernames[:20]:  # Limit to 20 for display
                    result_text += f"@{username}\n"
                
                if len(available_usernames) > 20:
                    result_text += f"\n... and {len(available_usernames) - 20} more!"
            else:
                result_text = get_text('no_available', lang)
            
            await status_msg.edit_text(
                result_text,
                reply_markup=create_main_keyboard(lang)
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

async def generate_usernames_with_progress(pattern: str, count: int, delay: float, 
                                         status_msg, lang: str) -> List[str]:
    """Generate usernames with progress updates and real-time results."""
    available_usernames = []
    checked_count = 0
    taken_count = 0
    
    async with TelegramUsernameChecker() as checker:
        for i in range(count):
            username = generate_username_from_pattern(pattern, lang)
            
            try:
                is_available = await checker.check_username(username)
                checked_count += 1
                
                if is_available:
                    available_usernames.append(username)
                    
                    # Show real-time results when found
                    if len(available_usernames) % 5 == 0 or len(available_usernames) <= 10:
                        current_results = ""
                        if available_usernames:
                            current_results = f"\n\n✅ {get_text('available_usernames', lang)}\n"
                            for username_found in available_usernames[-10:]:  # Show last 10
                                current_results += f"@{username_found}\n"
                            if len(available_usernames) > 10:
                                current_results += f"... and {len(available_usernames) - 10} more!"
                        
                        progress_text = get_text('checking_progress', lang,
                            current_checked=checked_count,
                            total_to_check=count,
                            available_count=len(available_usernames),
                            taken_count=taken_count,
                            remaining_count=count - checked_count
                        ) + current_results
                        
                        try:
                            await status_msg.edit_text(
                                progress_text,
                                reply_markup=create_home_keyboard(lang)
                            )
                        except Exception:
                            pass
                else:
                    taken_count += 1
                
                # Update progress every 10 checks or at the end
                if checked_count % 10 == 0 or checked_count == count:
                    current_results = ""
                    if available_usernames:
                        current_results = f"\n\n✅ {get_text('available_usernames', lang)}\n"
                        for username_found in available_usernames[-10:]:  # Show last 10
                            current_results += f"@{username_found}\n"
                        if len(available_usernames) > 10:
                            current_results += f"... and {len(available_usernames) - 10} more!"
                    
                    progress_text = get_text('checking_progress', lang,
                        current_checked=checked_count,
                        total_to_check=count,
                        available_count=len(available_usernames),
                        taken_count=taken_count,
                        remaining_count=count - checked_count
                    ) + current_results
                    
                    try:
                        await status_msg.edit_text(
                            progress_text,
                            reply_markup=create_home_keyboard(lang)
                        )
                    except Exception:
                        pass  # Ignore edit errors due to rate limits
                
                if delay > 0:
                    await asyncio.sleep(delay)
                    
            except Exception as e:
                logger.error(f"Error checking username {username}: {e}")
                continue
    
    return available_usernames

def generate_username_from_pattern(pattern: str, lang: str) -> str:
    """Generate username from pattern."""
    result = pattern
    
    # Handle quoted sections (fixed parts)
    quoted_parts = re.findall(r'"([^"]*)"', pattern)
    for quoted in quoted_parts:
        result = result.replace(f'"{quoted}"', quoted)
    
    # Replace x with random characters/digits
    while PLACEHOLDER_CHAR in result:
        char = random.choice(string.ascii_lowercase + string.digits)
        result = result.replace(PLACEHOLDER_CHAR, char, 1)
    
    return result

def generate_word_from_pattern(pattern: str, lang: str) -> str:
    """Generate word from pattern."""
    result = pattern
    
    # Handle quoted sections (fixed parts)
    quoted_parts = re.findall(r'"([^"]*)"', pattern)
    for quoted in quoted_parts:
        result = result.replace(f'"{quoted}"', quoted)
    
    # Replace x with random letters (not digits for words)
    while PLACEHOLDER_CHAR in result:
        if lang == 'ar':
            char = random.choice('ابتثجحخدذرزسشصضطظعغفقكلمنهوي')
        else:
            char = random.choice(string.ascii_lowercase)
        result = result.replace(PLACEHOLDER_CHAR, char, 1)
    
    return result

async def handle_word_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle word pattern or length input."""
    lang = get_language(context)
    text = update.message.text.strip()
    
    # Check if it's a pattern with 'x' or quoted parts
    if PLACEHOLDER_CHAR in text or '"' in text:
        context.user_data['word_pattern'] = text
        context.user_data['word_length'] = None
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
                context.user_data['word_pattern'] = None
                await update.message.reply_text(
                    get_text('word_count', lang),
                    reply_markup=create_home_keyboard(lang)
                )
                return ASK_WORD_COUNT
            else:
                await update.message.reply_text(
                    get_text('invalid_word_pattern', lang),
                    reply_markup=create_home_keyboard(lang)
                )
                return ASK_WORD_LENGTH
        except ValueError:
            await update.message.reply_text(
                get_text('invalid_word_pattern', lang),
                reply_markup=create_home_keyboard(lang)
            )
            return ASK_WORD_LENGTH

async def handle_word_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle word count input and generate words."""
    lang = get_language(context)
    
    try:
        count = int(update.message.text.strip())
        if 1 <= count <= 1000:
            length = context.user_data.get('word_length')
            pattern = context.user_data.get('word_pattern')
            
            if pattern:
                # Generate words using pattern
                words = []
                for _ in range(count):
                    word = generate_word_from_pattern(pattern, lang)
                    words.append(word)
            else:
                # Generate words using length
                generator = WordGenerator(lang)
                words = generator.generate_words(length=length, count=count)
            
            if words:
                result_text = f"{get_text('generated_words', lang)}\n\n"
                # Display words in chunks if too many
                display_count = min(100, len(words))
                for word in words[:display_count]:
                    result_text += f"• {word}\n"
                
                if len(words) > 100:
                    result_text += f"\n... and {len(words) - 100} more words generated!"
            else:
                result_text = get_text('no_available', lang)
            
            await update.message.reply_text(
                result_text,
                reply_markup=create_main_keyboard(lang)
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

async def handle_bulk_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bulk username list."""
    lang = get_language(context)
    text = update.message.text.strip()
    
    usernames = [line.strip().replace('@', '') for line in text.split('\n') if line.strip()]
    usernames = [u for u in usernames if u and len(u) >= 5 and len(u) <= 32]
    
    if not usernames or len(usernames) > 500:
        await update.message.reply_text(
            get_text('invalid_bulk_list', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return BULK_LIST
    
    status_msg = await update.message.reply_text(
        get_text('bulk_checking', lang, count=len(usernames)),
        reply_markup=create_home_keyboard(lang)
    )
    
    available_usernames = []
    checked_count = 0
    
    async with TelegramUsernameChecker() as checker:
        for username in usernames:
            try:
                is_available = await checker.check_username(username)
                checked_count += 1
                
                if is_available:
                    available_usernames.append(username)
                
                # Update progress
                if checked_count % 5 == 0 or checked_count == len(usernames):
                    progress_text = get_text('checking_progress', lang,
                        current_checked=checked_count,
                        total_to_check=len(usernames),
                        available_count=len(available_usernames),
                        taken_count=checked_count - len(available_usernames),
                        remaining_count=len(usernames) - checked_count
                    )
                    
                    try:
                        await status_msg.edit_text(
                            progress_text,
                            reply_markup=create_home_keyboard(lang)
                        )
                    except Exception:
                        pass
                
                await asyncio.sleep(0.1)  # Small delay to avoid rate limits
                
            except Exception as e:
                logger.error(f"Error checking username {username}: {e}")
                continue
    
    if available_usernames:
        result_text = f"{get_text('available_usernames', lang)}\n\n"
        for username in available_usernames[:30]:  # Limit display
            result_text += f"@{username}\n"
        
        if len(available_usernames) > 30:
            result_text += f"\n... and {len(available_usernames) - 30} more!"
    else:
        result_text = get_text('no_available', lang)
    
    await status_msg.edit_text(
        result_text,
        reply_markup=create_main_keyboard(lang)
    )
    
    return INITIAL_MENU

async def handle_bot_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bot username search."""
    lang = get_language(context)
    bot_name = update.message.text.strip().replace('@', '').lower()
    
    # Validate bot name
    if not re.match(r'^[a-zA-Z0-9_]+$', bot_name) or len(bot_name) < 3 or len(bot_name) > 28:
        await update.message.reply_text(
            get_text('invalid_bot_name', lang),
            reply_markup=create_home_keyboard(lang)
        )
        return ASK_BOT_SEARCH
    
    # Ensure bot suffix
    if not bot_name.endswith('bot'):
        bot_name += 'bot'
    
    status_msg = await update.message.reply_text(
        get_text('bot_search_results', lang, name=bot_name),
        reply_markup=create_home_keyboard(lang)
    )
    
    async with TelegramUsernameChecker() as checker:
        try:
            is_available = await checker.check_bot_username(bot_name.replace('bot', ''))
            
            if is_available:
                result_text = get_text('bot_available', lang, name=bot_name)
            else:
                result_text = get_text('bot_taken', lang, name=bot_name)
            
            await status_msg.edit_text(
                f"{get_text('bot_search_results', lang, name=bot_name)}\n\n{result_text}",
                reply_markup=create_main_keyboard(lang)
            )
            
        except Exception as e:
            logger.error(f"Error checking bot {bot_name}: {e}")
            await status_msg.edit_text(
                get_text('error_occurred', lang, error=str(e)),
                reply_markup=create_main_keyboard(lang)
            )
    
    return INITIAL_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation."""
    lang = get_language(context)
    await update.message.reply_text(
        get_text('welcome', lang),
        reply_markup=create_main_keyboard(lang)
    )
    return INITIAL_MENU

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    if isinstance(context.error, RetryAfter):
        logger.warning(f"Rate limit hit, retry after {context.error.retry_after} seconds")
        await asyncio.sleep(context.error.retry_after)

def main():
    """Start the bot."""
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            INITIAL_MENU: [CallbackQueryHandler(button_handler)],
            ASK_USERNAME_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username_count),
                CallbackQueryHandler(button_handler)
            ],
            ASK_PATTERN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pattern),
                CallbackQueryHandler(button_handler)
            ],
            ASK_DELAY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delay),
                CallbackQueryHandler(button_handler)
            ],
            ASK_WORD_LENGTH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_word_length),
                CallbackQueryHandler(button_handler)
            ],
            ASK_WORD_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_word_count),
                CallbackQueryHandler(button_handler)
            ],
            BULK_LIST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bulk_list),
                CallbackQueryHandler(button_handler)
            ],
            ASK_BOT_SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bot_search),
                CallbackQueryHandler(button_handler)
            ],
            HOW_TO_INFO: [CallbackQueryHandler(button_handler)],
            SET_LANGUAGE: [CallbackQueryHandler(button_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )
    
    # Add handlers
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("Starting RipperTek Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()