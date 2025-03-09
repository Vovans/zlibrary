import os
import asyncio
import logging
import re
from zlibrary import AsyncZlib
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
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

        messages = []
        reply = limits_text  # Prepend limits info to the first message
        max_length = 3000  # Telegram's limit is 4096, leaving margin
        books_per_message = 3  # Max books per message

        for idx, book_item in enumerate(paginator.result, start=1):
            book = await book_item.fetch()
            title = book.get("name", "Unknown")[:100]
            authors = book.get("authors", [])
            logging.debug(f"Raw authors data: {authors}")
            if isinstance(authors, list) and authors:
                # Use only first author
                author_info = authors[0]
                author_names = author_info.get("author", "Unknown")
            else:
                author_names = "Unknown Author"
            logging.debug(f"Extracted author names: {author_names}")
            format_type = book.get("extension", "Unknown")
            
            if not context.application.zlib or not context.application.zlib.cookies:
                logging.error("Z-Library session is not authenticated! Ensure login credentials are set.")

            original_url = book.get("download_url", "Unavailable")
            final_url = original_url  # Fallback if redirect fails

            if original_url.startswith("https://z-library.sk/dl/"):
                logging.debug(f"Following redirect for: {original_url}")
                try:
                    response = await context.application.zlib._r_raw(original_url)
                    logging.debug(f"Received response status: {response.status}")
                    # Use response.url to get final URL without decoding content
                    final_url = str(response.url)
                    if response.history:
                        logging.debug(f"Final redirect resolved URL: {final_url}")
                    else:
                        logging.warning(f"No redirects detected; using original URL: {final_url}")
                except Exception as e:
                    logging.error(f"Failed to retrieve final URL: {e}")
                    final_url = original_url

            logging.debug(f"Using final download URL: {final_url}")
            download_link = escape_url(final_url)

            safe_title = escape_markdown(title)
            safe_author_names = escape_markdown(author_names)
            safe_format_type = escape_markdown(format_type)

            entry = (
                f"*{idx}\\. {safe_title}*\n"
                f"Author\\(s\\): {safe_author_names}\n"
                f"Format: {safe_format_type}\n"
                f"[Download]({download_link})\n\n"
            )

            logging.debug(f"DEBUG Entry content: {entry}")
            logging.debug(f"DEBUG Entry length: {len(entry)}")
            logging.debug(f"DEBUG Current reply length: {len(reply)}")
            if len(reply) + len(entry) > max_length or (idx % books_per_message == 0):
                if reply.strip():
                    messages.append(reply)
                    logging.debug(f"DEBUG: Sending message of length: {len(reply)}")
                    await update.message.reply_text(reply, parse_mode="MarkdownV2", disable_web_page_preview=True)
                reply = entry
            else:
                reply += entry

        if reply.strip():
            logging.debug(f"Final message being sent: {reply}")
            messages.append(reply)
            await update.message.reply_text(reply, parse_mode="MarkdownV2", disable_web_page_preview=True)
        elif not messages:
            await update.message.reply_text("No results found.")
    else:
        await update.message.reply_text("No results found.")

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

    loop = asyncio.get_event_loop()
    zlib = loop.run_until_complete(zlib_login())

    if not zlib:
        return

    application.zlib = zlib

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), search_books))

    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()