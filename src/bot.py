```python
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
            return  # Ignore messages in groups unless the bot is mentioned

        query = query.replace(f"@{bot_username}", "").strip()
    paginator = await context.application.zlib.search(q=query, count=5)
    await paginator.next()

    if paginator.result:
        messages = []
        reply = ""
        max_length = 3000  # Telegram's limit is 4096, leaving margin
        books_per_message = 3  # Max books in one message

        for idx, book_item in enumerate(paginator.result, start=1):
            book = await book_item.fetch()
            title = book.get("name", "Unknown")[:100]
            authors = book.get("authors", [])
            logging.debug(f"Raw authors data: {authors}")
            if isinstance(authors, list) and authors:
                author_info = authors[0]
                author_names = author_info.get("author", "Unknown")
            else:
                author_names = "Unknown Author"
            logging.debug(f"Extracted author names: {author_names}")
            format_type = book.get("extension", "Unknown")
            
            # Verify authentication before retrieving download link
            if not context.application.zlib or not context.application.zlib.cookies:
                logging.error("Z-Library session is not authenticated! Ensure login credentials are set.")

            # Attempt to follow redirect to get final download URL
            original_url = book.get("download_url", "Unavailable")
            final_url = original_url  # Default to original URL if redirect fails

            if original_url.startswith("https://z-library.sk/dl/"):
                logging.debug(f"Following redirect for: {original_url}")
                try:
                    response = await context.application.zlib._r_raw(original_url)
                    logging.debug(f"Received response status: {response.status}")
                    
                    # Extract final URL without decoding content
                    final_url = str(response.url)

                    if response.history:  # Check if redirects happened
                        logging.debug(f"Final redirect resolved URL: {final_url}")
                    else:
                        logging.warning(f"No redirects detected; using original URL: {final_url}")

                except Exception as e:
                    logging.error(f"Failed to retrieve final URL: {e}")
                    final_url = original_url  # Fallback to original URL

            logging.debug(f"Using final download URL: {final_url}")
            download_link = escape_url(final_url)

            # Escape special characters in title and author names
            safe_title = escape_markdown(title)
            safe_author_names = escape_markdown(author_names)
            safe_format_type = escape_markdown(format_type)

            # Format messages with bold title and clickable download link
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
                if reply.strip():  # Ensure reply contains valid content
                    messages.append(reply)
                    logging.debug(f"DEBUG: Sending message of length: {len(reply)}")  # Log sent message length
                    await update.message.reply_text(reply, parse_mode="MarkdownV2", disable_web_page_preview=True)
                reply = entry  # Start new buffer with current entry
            else:
                reply += entry  # Add new entry to reply buffer

        # Ensure last accumulated message is sent
        if reply.strip():
            logging.debug(f"Final message being sent: {reply}")
            messages.append(reply)
            await update.message.reply_text(reply, parse_mode="MarkdownV2", disable_web_page_preview=True)
        elif not messages:
            await update.message.reply_text("No results found.")  # Ensure a response is always sent
    else:
        await update.message.reply_text("No results found.")  # In case paginator.result is empty

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

    # Create the Telegram bot application
    application = ApplicationBuilder().token(telegram_token).build()

    # Perform the zlibrary login asynchronously
    loop = asyncio.get_event_loop()
    zlib = loop.run_until_complete(zlib_login())

    if not zlib:
        return

    # Store zlib instance in application
    application.zlib = zlib

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), search_books))

    # Run the bot
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
```