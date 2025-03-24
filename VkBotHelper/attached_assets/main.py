import logging
import os
import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from telegram.ext import Application, MessageHandler, filters
from telegram import Update
from dotenv import load_dotenv

from handlers import (
    handle_media_group,
    handle_photo_video,
    handle_document,
    handle_audio,
    handle_text,
    handle_edited_message
)

# Загружаем переменные окружения
load_dotenv()

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Отключаем лишние логи
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

# Создаем директорию для файлов
os.makedirs('./files', exist_ok=True)

async def main():
    """Основная функция запуска бота"""
    try:
        # Инициализируем бота
        application = Application.builder().token(os.getenv('TELEGRAM_API_TOKEN')).build()
        
        # Регистрируем обработчики
        application.add_handler(MessageHandler(
            filters.ChatType.CHANNEL & filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.DOCUMENT | filters.TEXT,
            handle_media_group
        ))
        
        application.add_handler(MessageHandler(
            filters.ChatType.CHANNEL & (filters.PHOTO | filters.VIDEO) & ~filters.MediaGroupFilter(),
            handle_photo_video
        ))
        
        application.add_handler(MessageHandler(
            filters.ChatType.CHANNEL & filters.DOCUMENT & ~filters.MediaGroupFilter(),
            handle_document
        ))
        
        application.add_handler(MessageHandler(
            filters.ChatType.CHANNEL & filters.AUDIO & ~filters.MediaGroupFilter(),
            handle_audio
        ))
        
        application.add_handler(MessageHandler(
            filters.ChatType.CHANNEL & filters.TEXT & ~filters.MediaGroupFilter(),
            handle_text
        ))
        
        application.add_handler(MessageHandler(
            filters.ChatType.CHANNEL & filters.UpdateType.EDITED_CHANNEL_POST,
            handle_edited_message
        ))
        
        # Запускаем бота
        await application.initialize()
        await application.start()
        await application.run_polling()
        
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
    finally:
        await application.stop()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())