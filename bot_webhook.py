import logging
import os
import random
import string # تم نقل الاستيراد إلى هنا لأفضل الممارسات

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# 💬 Logging
# تم تصحيح 'name' إلى '__name__'
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ Environment token
# تأكد من تعيين هذا المتغير في Railway.
# لا تستخدم "YOUR_REAL_TOKEN_HERE" في بيئة الإنتاج.
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    logger.error("TELEGRAM_TOKEN environment variable not set!")
    # قد ترغب في إيقاف التطبيق أو التعامل مع الخطأ بطريقة أخرى إذا كان التوكن غير موجود
    # For local testing, you might uncomment the line below, but NEVER for production
    # TOKEN = "YOUR_REAL_TOKEN_HERE" # استخدم هذا فقط للاختبار المحلي إذا لم تكن تستخدم متغيرات البيئة


# 📍 States
ASK_EXAMPLE, BULK_LIST = range(2)

# 🎛️ Start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔤 Generate Username", callback_data='generate')],
        [InlineKeyboardButton("📄 Bulk Check List", callback_data='bulk')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to RipperTek Bot. Please choose:", reply_markup=reply_markup)

# ☑️ Button handling
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'generate':
        await query.edit_message_text("Send a sample pattern (like a_b_c):")
        return ASK_EXAMPLE
    elif query.data == 'bulk':
        await query.edit_message_text("Send a list of usernames (one per line):")
        return BULK_LIST
    # إضافة حالة افتراضية لضمان عدم حدوث خطأ إذا كانت query.data غير متوقعة
    return ConversationHandler.END


# 🔤 Generate based on example
async def ask_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = update.message.text.strip()
    generated = generate_usernames(pattern)
    # عرض 20 اسم مستخدم فقط لتجنب الرسائل الطويلة جداً
    await update.message.reply_text("Generated usernames (showing first 20 available):\n" + "\n".join(generated[:20]))
    return ConversationHandler.END

# 📋 Bulk checker
async def bulk_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [name.strip() for name in update.message.text.strip().splitlines() if name.strip()] # إزالة الفراغات والأسطر الفارغة
    available = [name for name in names if check_username(name)]
    if available:
        await update.message.reply_text("✅ Available:\n" + "\n".join(available))
    else:
        await update.message.reply_text("😔 No usernames found available from your list.")
    return ConversationHandler.END

# 🧠 Username generator
# تم نقل 'import string' إلى بداية الملف
def generate_usernames(pattern):
    # قم بتحسين هذه الدالة إذا كانت تستهلك الكثير من الوقت أو الذاكرة
    # (مثلاً، إذا كانت تولد عدداً كبيراً جداً من الأسماء قبل التحقق)
    letters = string.ascii_lowercase
    result = []
    # يجب أن يكون هذا المنطق أكثر ذكاءً. حالياً، يقوم باستبدال 'a','b','c' فقط.
    # إذا كانت النماذج أكثر تعقيدًا (مثل 'x_y_z')، فلن يعمل هذا.
    # قد تحتاج إلى تحديد علامات خاصة في النمط (مثل {1}, {2}) بدلاً من حروف ثابتة.
    for char1 in letters:
        for char2 in letters:
            for char3 in letters:
                # هذا الافتراض بأن النمط يحتوي دائماً على 'a', 'b', 'c' قد لا يكون دقيقاً.
                # تحتاج إلى منطق أكثر مرونة لاستبدال الحروف في النمط.
                # مثال بسيط جداً لتوضيح الفكرة (افترض النمط 'a_b_c'):
                uname = pattern.replace('a', char1, 1).replace('b', char2, 1).replace('c', char3, 1)

                # يمكنك إضافة قيود هنا قبل التحقق (طول، أحرف مسموحة، إلخ)
                if check_username(uname):
                    result.append(uname)
                    if len(result) >= 100: # لنتوقف عند أول 100 اسم متاح
                        return result
    return result

# 🔍 Simulated username check (you can replace with actual API request)
