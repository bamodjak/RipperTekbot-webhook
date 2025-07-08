import logging
import os
import random
import string

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
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
    raise RuntimeError("TELEGRAM_TOKEN environment variable not set!")

# States
# تم إضافة INITIAL_MENU
INITIAL_MENU, ASK_EXAMPLE, BULK_LIST = range(3)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔤 Generate Username", callback_data='generate')],
        [InlineKeyboardButton("📄 Bulk Check List", callback_data='bulk')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to RipperTek Bot. Please choose:", reply_markup=reply_markup)
    return INITIAL_MENU # <--- مهم: نرجع الحالة بعد إرسال الأزرار

# Callback query handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'generate':
        await query.edit_message_text("Send a sample pattern (e.g., a_b_c):")
        return ASK_EXAMPLE
    elif query.data == 'bulk':
        await query.edit_message_text("Send a list of usernames (one per line):")
        return BULK_LIST
    elif query.data == 'back': # <--- إضافة منطق لزر "Back"
        await query.edit_message_text("Welcome to RipperTek Bot. Please choose:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔤 Generate Username", callback_data='generate')],
            [InlineKeyboardButton("📄 Bulk Check List", callback_data='bulk')]
        ]))
        return INITIAL_MENU # العودة إلى حالة القائمة الأولية

    return ConversationHandler.END

# Username generator logic
# ... (لا تغيير) ...
def generate_usernames(pattern, limit=20):
    letters = string.ascii_lowercase + string.digits
    generated = set()

    while len(generated) < limit:
        uname = pattern
        # هذا الجزء من الكود قد يكون معقداً بعض الشيء في التعامل مع النمط
        # الأفضل هو البحث عن placeholder معين مثل {} أو {a} {b}
        # الطريقة الحالية تفترض استبدال أول ظهور لـ 'a' ثم 'b' ثم 'c'
        # قد تحتاج لتحسينها لتكون أكثر شمولية لأنماط مختلفة.
        # مثلاً: pattern.replace('A', random.choice(letters), 1)
        # هذا يحتاج لتوضيح أكثر حول ما هو النمط الذي تتوقعه "a_b_c"
        # إذا كان القصد هو استبدال 'a' في النمط، ثم 'b' في النمط، وهكذا.
        # هذا الكود سيقوم باستبدال "a" واحدة فقط، ثم "b" واحدة فقط، وهكذا.
        # قد لا يعطي النتائج المتوقعة لو كان النمط "aaa" مثلاً.
        # سأتركه كما هو حالياً لكن أضع ملاحظة عليه.
        for char_to_replace in ['a', 'b', 'c']: # نأخذ الأحرف المحددة في النمط
             if char_to_replace in uname: # نتأكد أنها موجودة في النمط
                uname = uname.replace(char_to_replace, random.choice(letters), 1)

        if uname not in generated:
            generated.add(uname)

    return list(generated)


# Telegram API username availability checker
async def check_username_availability(context, username):
    # تحقق من طول اسم المستخدم (5-32 حرف) والأحرف المسموحة
    if not (5 <= len(username) <= 32 and username.replace('_', '').isalnum()):
        logger.warning(f"Invalid username format or length: {username}")
        return False

    try:
        # get_chat قد ينجح أيضاً لأسماء قنوات غير متاحة لكنها موجودة كقناة خاصة
        # الطريقة الأكثر دقة هي محاولة إنشاء قناة / مجموعة
        # لكن get_chat هو الأسهل للبدء به.
        chat = await context.bot.get_chat(f"@{username}")
        # إذا كانت المحادثة موجودة وكانت عامة (لها username)، فهي غير متاحة
        if chat.username and chat.username.lower() == username.lower():
            logger.info(f"Username @{username} already exists (get_chat successful).")
            return False
        # في بعض الحالات، قد ينجح get_chat لـ usernames غير عامة (خاصة).
        # هنا قد تحتاج لتمييز دقيق، ولكن بشكل عام هذا يعني أن الاسم مستخدم.
        return False
    except BadRequest as e:
        # Telegram API يرجع BadRequest عندما لا يجد اسم المستخدم.
        error_message = str(e).lower()
        if "username not found" in error_message or "chat not found" in error_message:
            logger.info(f"Username @{username} is likely available (BadRequest: {error_message}).")
            return True
        logger.error(f"Error checking username {username}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking username {username}: {e}")

    return False

# Handle generated pattern
# ... (لا تغيير) ...
async def ask_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = update.message.text.strip()
    raw_usernames = generate_usernames(pattern, limit=100) # يولد 100 محاولة

    available = []
    for uname in raw_usernames:
        # هنا يجب إضافة تأخير بسيط بين كل طلب لـ Telegram API لتجنب FloodWait
        # مثلاً: await asyncio.sleep(0.1)
        if await check_username_availability(context, uname):
            available.append(uname)
            if len(available) >= 20: # يعرض أول 20 متاحاً
                break

    if available:
        text = "✅ First 20 available usernames:\n" + "\n".join(available)
    else:
        text = "😔 No available usernames found."

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# Handle bulk checking
# ... (لا تغيير) ...
async def bulk_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [n.strip() for n in update.message.text.splitlines() if n.strip()]
    available = []

    for name in names:
        # هنا أيضاً يجب إضافة تأخير بسيط بين كل طلب
        if await check_username_availability(context, name):
            available.append(name)

    if available:
        text = "✅ Available usernames:\n" + "\n".join(available)
    else:
        text = "😔 None are available."

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# Cancel
# ... (لا تغيير) ...
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# Webhook or Polling start
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        # المحادثة تبدأ الآن بأمر /start
        entry_points=[CommandHandler("start", start)],
        states={
            # بعد أمر /start، ننتظر ضغطة زر في حالة INITIAL_MENU
            INITIAL_MENU: [CallbackQueryHandler(button)],
            ASK_EXAMPLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_example)],
            BULK_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_list)],
        },
        # أضف 'back' كfallback للحالات إذا كنت تريد أن يعود الزر "Back" من أي مكان
        # أو تعامل معه داخل كل حالة
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button, pattern="^back$")], # <--- يمكن إضافة هذا لمعالجة زر "Back" في أي حالة
    )

    # أضف الـ ConversationHandler فقط
    app.add_handler(conv_handler)

    # Webhook config
    PORT = int(os.getenv("PORT", "8080"))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    WEBHOOK_SECRET_PATH = os.getenv("WEBHOOK_SECRET_PATH", f"webhook_{os.urandom(16).hex()}")

    if WEBHOOK_URL:
        logger.info(f"Starting Webhook at {WEBHOOK_URL}/{WEBHOOK_SECRET_PATH}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_SECRET_PATH,
            webhook_url=f"{WEBHOOK_URL}/{WEBHOOK_SECRET_PATH}"
        )
    else:
        logger.warning("No WEBHOOK_URL set. Running in polling mode.")
        app.run_polling()
