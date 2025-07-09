# main.py - All-in-one Telegram Gift Bot (NOT RECOMMENDED FOR LARGER PROJECTS)

import logging
import os
import sys
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters
)

# --- Configuration (from Environment Variables) ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USER_ID_STR = os.environ.get("ADMIN_USER_ID")
ADMIN_USER_ID = int(ADMIN_USER_ID_STR) if ADMIN_USER_ID_STR else None

if not BOT_TOKEN:
    logging.error("BOT_TOKEN environment variable not set. Exiting.")
    sys.exit(1)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Gift Data (Moved directly into this file) ---
GIFTS = {
    "happy_star": {
        "name": "Happy Star",
        "file_path": "animations/happy_star.tgs", # Still needs the animations folder
        "price_stars": 10,
        "description": "A sparkling star sending happy vibes!",
    },
    "cute_heart": {
        "name": "Cute Heart",
        "file_path": "animations/cute_heart.tgs", # Still needs the animations folder
        "price_stars": 20,
        "description": "A lovely heart for your special ones.",
    },
    # Add more gifts here
}

# --- Handlers (remain the same) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! 👋\n"
        "Welcome to your fun gift bot! You can buy unique animated gifts here.\n\n"
        "Use /gifts to see what's available."
    )

async def show_gifts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard_buttons = []
    for gift_id, gift_data in GIFTS.items():
        keyboard_buttons.append(
            [InlineKeyboardButton(f"{gift_data['name']} ({gift_data['price_stars']}⭐)", callback_data=f"show_gift_{gift_id}")]
        )
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    await update.message.reply_text("Here are the gifts available:", reply_markup=reply_markup)

async def show_gift_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    gift_id = query.data.replace("show_gift_", "")
    gift_data = GIFTS.get(gift_id)

    if not gift_data:
        await query.edit_message_text("Sorry, that gift was not found.")
        return

    if not os.path.exists(gift_data["file_path"]):
        await query.edit_message_text(
            f"Error: Gift animation file not found for {gift_data['name']} at {gift_data['file_path']}. Please inform the bot admin."
        )
        logger.error(f"Missing gift file: {gift_data['file_path']}")
        if ADMIN_USER_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_USER_ID,
                    text=f"CRITICAL: Missing gift animation file for {gift_data['name']} at {gift_data['file_path']}"
                )
            except Exception as e:
                logger.error(f"Failed to notify admin about missing file: {e}")
        return

    try:
        with open(gift_data["file_path"], "rb") as f:
            await context.bot.send_sticker(
                chat_id=query.message.chat_id,
                sticker=f,
                filename=os.path.basename(gift_data["file_path"])
            )
    except Exception as e:
        logger.error(f"Failed to send sticker {gift_data['file_path']}: {e}")
        await query.message.reply_text("Could not send the gift animation. There might be an issue with the file.")
        return

    keyboard = [[InlineKeyboardButton(f"Buy {gift_data['name']} for {gift_data['price_stars']} ⭐", callback_data=f"buy_gift_{gift_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        f"**{gift_data['name']}**\n\n"
        f"{gift_data['description']}\n\n"
        f"Price: {gift_data['price_stars']} Telegram Stars ⭐",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def buy_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    gift_id = query.data.replace("buy_gift_", "")
    gift_data = GIFTS.get(gift_id)

    if not gift_data:
        await query.edit_message_text("Sorry, that gift was not found.")
        return

    chat_id = query.message.chat_id
    title = f"Purchase {gift_data['name']}"
    description = f"Get your exclusive animated gift: {gift_data['name']}"
    currency = "XTR"
    price = gift_data["price_stars"] * 100

    prices = [LabeledPrice(label=gift_data["name"], amount=price)]
    payload = f"{query.from_user.id}_{gift_id}_{int(update.effective_message.date.timestamp())}"

    await context.bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",
        currency=currency,
        prices=prices,
        start_parameter="start_param",
        need_shipping_address=False,
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    invoice_payload = update.message.successful_payment.invoice_payload
    currency = update.message.successful_payment.currency
    total_amount = update.message.successful_payment.total_amount / 100

    logger.info(f"Successful payment from {user.id} for payload: {invoice_payload}")
    logger.info(f"Amount: {total_amount} {currency}")

    try:
        _, gift_id, _ = invoice_payload.split('_')
        gift_data = GIFTS.get(gift_id)
        if gift_data:
            with open(gift_data["file_path"], "rb") as f:
                await context.bot.send_sticker(
                    chat_id=update.effective_chat.id,
                    sticker=f,
                    filename=os.path.basename(gift_data["file_path"]),
                    caption=f"🎉 Congratulations, {user.first_name}! You've successfully purchased the '{gift_data['name']}'! Enjoy your gift!"
                )
            logger.info(f"Gift '{gift_id}' delivered to user {user.id}.")
        else:
            await update.message.reply_text("Payment successful, but gift details not found. Please contact support.")
            logger.error(f"Gift data not found for successful payment payload: {invoice_payload}")

    except Exception as e:
        logger.error(f"Error processing successful payment for payload {invoice_payload}: {e}")
        await update.message.reply_text("Payment successful, but there was an error delivering the gift. Please contact support.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)
    if ADMIN_USER_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"An error occurred:\n\n`{context.error}`\n\nUpdate: `{update}`",
                parse_mode="MarkdownV2"
            )
        except Exception as e:
            logger.error(f"Failed to send error notification to admin: {e}")
    if update.effective_chat:
        await update.effective_chat.send_message("Oops! Something went wrong. Please try again later.")

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("gifts", show_gifts))
    application.add_handler(CallbackQueryHandler(show_gift_details, pattern=r"^show_gift_"))
    application.add_handler(CallbackQueryHandler(buy_gift, pattern=r"^buy_gift_"))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    application.add_handler(error_handler)

    logger.info("Bot is starting polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    if not os.path.exists("animations"):
        os.makedirs("animations")
        logger.info("Created 'animations' directory. Please place your .tgs files there.")
    main()
