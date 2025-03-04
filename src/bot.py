import os
import asyncio
import logging
from zlibrary import AsyncZlib
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(filename="zlibrary_bot.log", level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! Send me a message with your search query, and I will find books for you."
    )

async def search_books(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip().lower()

    if update.message.chat.type in ["group", "supergroup"]:
        bot_username = (await context.bot.get_me()).username.lower()
        if f"@{bot_username}" not in query:
            return  # Ignore messages in groups unless the bot is mentioned

        query = query.replace(f"@{bot_username}", "").strip()
    paginator = await context.application.zlib.search(q=query, count=5)
    await paginator.next()

    if paginator.result:
        messages = []
        reply = ""
        max_length = 3000  # Telegram's limit is 4096, leaving margin
        books_per_message = 3  # Max books in one message

        for i, book_item in enumerate(paginator.result, start=1):
            book = await book_item.fetch()
            title = book.get("name", "Unknown")[:100]
            authors = book.get("authors", [])
            logging.debug(f"Raw authors data: {authors}")
            author_names = authors[0].get("author", "Unknown") if isinstance(authors, list) and authors else "Unknown Author"
            logging.debug(f"Extracted author names before trimming: {author_names}")           
            format_type = book.get("extension", "Unknown")
            # Attempt to follow redirect to get final download URL
            original_url = book.get("download_url", "Unavailable")
            final_url = original_url  # Default to original URL if redirect fails

            if original_url.startswith("https://z-library.sk/dl/"):
                logging.debug(f"Following redirect for: {original_url}")
                try:
                    response = await context.application.zlib._r(original_url)  # Await response object
                    if response.status == 200:
                        final_url = str(response.url)  # Extract final redirected URL
                        logging.debug(f"Resolved final redirect URL: {final_url}")
                    else:
                        logging.warning(f"Unexpected status {response.status} when following redirect.")
                except Exception as e:
                    logging.error(f"Failed to retrieve final URL: {e}")

            logging.debug(f"Using final download URL: {final_url}")
            
            logging.debug(f"Resolved final download URL: {final_url}")
            download_link = final_url

            entry = f"{i}. {title}\nAuthor(s): {author_names}\nFormat: {format_type}\nDownload: {download_link}\n\n"
            
            logging.debug(f"DEBUG Entry content: {entry}")
            logging.debug(f"DEBUG Entry length: {len(entry)}")
            logging.debug(f"DEBUG Current reply length: {len(reply)}")
            if len(reply) + len(entry) > max_length or (i % books_per_message == 0):
                if reply.strip():  # Ensure reply contains valid content
                    messages.append(reply)
                    print(f"DEBUG: Sending message of length: {len(reply)}")  # Log sent message length
                    await update.message.reply_text(reply)  # Send message immediately
                reply = entry  # Start new buffer with current entry
            else:
                reply += entry  # Add new entry to reply buffer

        # Ensure last accumulated message is sent
        if reply.strip():
            logging.debug(f"Final message being sent: {reply}")
            messages.append(reply)
            await update.message.reply_text(reply)
        elif not messages:
            await update.message.reply_text("No results found.")  # Ensure a response is always sent

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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    zlib = loop.run_until_complete(zlib_login())

    if not zlib:
        return

    # Store zlib instance in application
    application.zlib = zlib

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP), search_books))

    # Run the bot
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()