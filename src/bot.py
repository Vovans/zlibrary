import os
import asyncio
from zlibrary import AsyncZlib
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

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
        max_length = 4000  # Telegram's limit is 4096, leaving margin
        books_per_message = 3  # Reduce books per message

        for i, book_item in enumerate(paginator.result, start=1):
            book = await book_item.fetch()
            title = book.get("name", "Unknown")[:100]
            authors = book.get("authors", [])
            author_names = ", ".join([author.get("author", "Unknown")[:30] for author in authors]) if isinstance(authors, list) else "Unknown Author"
            format_type = book.get("extension", "Unknown")
            download_link = book.get("download_url", "Unavailable")

            entry = f"{i}. {title}\nAuthor(s): {author_names}\nFormat: {format_type}\nDownload: {download_link}\n\n"

        if len(reply) + len(entry) > max_length or (i % books_per_message == 0):
            if reply.strip():  # Ensure reply is not empty before sending
                messages.append(reply)
                await update.message.reply_text(reply)
            reply = entry  # Start a new message batch
        else:
            reply += entry

        # Send the last message after processing all loops
        if reply.strip():
            await update.message.reply_text(reply)

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