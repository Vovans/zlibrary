import os
import asyncio
import logging
import re
import uuid
from zlibrary import AsyncZlib
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

logging.basicConfig(
    filename="zlibrary_bot.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

def escape_markdown(text):
    """
    Helper function to escape telegram markup symbols as per Telegram's MarkdownV2 requirements.
    """
    escape_chars = r'([\_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.\!])'
    return re.sub(escape_chars, r'\\\1', text)

def escape_url(url):
    """
    Escapes special characters in URLs as per Telegram's MarkdownV2 requirements.
    """
    return url.replace(')', '\\)')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! Send me a message with your search query, and I will find books for you."
    )

async def search_books(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()

    if update.message.chat.type in ["group", "supergroup"]:
        bot_username = (await context.bot.get_me()).username.lower()
        if f"@{bot_username}" not in query.lower():
            return  # Ignore messages in groups unless bot is mentioned

        query = query.replace(f"@{bot_username}", "").strip()
    paginator = await context.application.zlib.search(q=query, count=5)
    await paginator.next()

    if paginator.result:
        # Get download limits info from profile
        try:
            limit_info = await context.application.zlib.profile.get_limits()
            limits_text = (
                f"Download Limits: Used {limit_info['daily_amount']} / Allowed {limit_info['daily_allowed']}, "
                f"Remaining {limit_info['daily_remaining']}, Reset at: {limit_info['daily_reset']}\n\n"
            )
        except Exception as e:
            logging.error(f"Failed to retrieve download limits: {e}")
            limits_text = ""

        reply = limits_text  # Prepend limits info
        max_length = 3000  # Leave margin for Telegram (actual limit is 4096)
        buttons = []  # Collect inline keyboard buttons for each book entry

        for idx, book_item in enumerate(paginator.result, start=1):
            book = await book_item.fetch()
            title = book.get("name", "Unknown")[:100]
            authors = book.get("authors", [])
            logging.debug(f"Raw authors data: {authors}")
            if isinstance(authors, list) and authors:
                # Use only the first author
                author_info = authors[0]
                author_names = author_info.get("author", "Unknown")
            else:
                author_names = "Unknown Author"
            logging.debug(f"Extracted author names: {author_names}")
            format_type = book.get("extension", "Unknown")

            original_url = book.get("download_url", "Unavailable")
            # Do not resolve the link now; we will resolve it upon button click.
            final_url = original_url

            safe_title = escape_markdown(title)
            safe_author_names = escape_markdown(author_names)
            safe_format_type = escape_markdown(format_type)

            entry = (
                f"*{idx}\\. {safe_title}*\n"
                f"Author\\(s\\): {safe_author_names}\n"
                f"Format: {safe_format_type}\n"
            )
            # Append the entry text to reply
            if len(reply) + len(entry) > max_length:
                if reply.strip():
                    await update.message.reply_text(reply, parse_mode="MarkdownV2", disable_web_page_preview=True)
                reply = entry
            else:
                reply += entry

            # Generate a unique token and store the original_url in the mapping for later resolution.
            token = uuid.uuid4().hex
            if not hasattr(context.application, "link_mapping"):
                context.application.link_mapping = {}
            context.application.link_mapping[token] = original_url

            # Create an inline keyboard button for resolving the download link.
            button = InlineKeyboardButton(f"Show link for {idx}", callback_data=f"show_link:{token}")
            buttons.append([button])  # Each button in its own row

            reply += "\n"  # Add extra newline after entry

        # Send the search results message with inline keyboard buttons if any.
        await update.message.reply_text(reply, parse_mode="MarkdownV2", disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text("No results found.")

async def resolve_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for 'Show link' button; resolves the original download URL."""
    query = update.callback_query
    await query.answer()  # Acknowledge callback
    data = query.data  # Expected format: "show_link:<token>"
    try:
        token = data.split(":", 1)[1]
    except IndexError:
        await query.edit_message_text("Invalid callback data.")
        return

    original_url = context.application.link_mapping.get(token)
    if not original_url:
        await query.edit_message_text("Link not found or expired.")
        return

    try:
        response = await context.application.zlib._r_raw(original_url)
        final_url = str(response.url)
        # Remove the token from the mapping once used.
        context.application.link_mapping.pop(token, None)
        safe_final_url = escape_url(final_url)
        message_text = f"Resolved Download Link: [Download]({safe_final_url})"
        await query.edit_message_text(message_text, parse_mode="MarkdownV2", disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Failed to resolve link for token {token}: {e}")
        await query.edit_message_text("Failed to resolve the download link.")

async def zlib_login():
    """Handle the asynchronous login for zlibrary."""
    zlibrary_email = os.environ.get("ZLOGIN")
    zlibrary_password = os.environ.get("ZPASSW")

    if not zlibrary_email or not zlibrary_password:
        print("Please set the environment variables ZLOGIN and ZPASSW.")
        return None

    zlib = AsyncZlib()
    await zlib.login(zlibrary_email, zlibrary_password)
    return zlib

def main():
    """Initializes the bot and runs it."""
    telegram_token = os.environ.get("TELEGRAM_TOKEN")

    if not telegram_token:
        print("Please set the environment variable TELEGRAM_TOKEN.")
        return

    application = ApplicationBuilder().token(telegram_token).build()
    # Initialize global mapping for link resolution.
    application.link_mapping = {}

    loop = asyncio.get_event_loop()
    zlib = loop.run_until_complete(zlib_login())

    if not zlib:
        return

    application.zlib = zlib

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), search_books))
    application.add_handler(CallbackQueryHandler(resolve_link, pattern=r"^show_link:"))

    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()