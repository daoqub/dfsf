import os
import logging
import time
import shutil
import datetime
import requests
from dotenv import load_dotenv
from supabase import create_client, Client
from vk_api import VkApi
from vk_api.utils import get_random_id

load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Отключаем лишнее логирование
logging.getLogger('supabase').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

# Инициализация Supabase
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Настройка директорий
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

# Константы
TELEGRAM_API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
VK_API_TOKEN = os.getenv('VK_API_TOKEN')
VK_GROUP_ID = os.getenv('VK_GROUP_ID')

# Глобальные переменные для работы с клиентами
supabase = None
vk = None
uploader = None
telegram_client = None

def format_owner_id(target_id):
    """Форматирует ID группы ВКонтакте в правильный формат owner_id"""
    try:
        # Преобразуем в строку и убираем все пробелы
        str_id = str(target_id).strip()
        
        # Убедимся, что ID группы начинается с минуса
        if str_id.startswith('-'):
            # Уже начинается с минуса - преобразуем в целое число
            return int(str_id)
        else:
            # Если ID положительный, добавляем минус для групп
            return -1 * int(str_id)
    except (ValueError, TypeError) as e:
        logging.error(f"Ошибка при форматировании owner_id: {e}")
        # Возвращаем строку с минусом в случае ошибки, чтобы избежать дополнительных ошибок
        return f"-{target_id}"

def refresh_token_if_needed():
    """Проверяет и обновляет токен VK API при необходимости"""
    try:
        global vk
        if not vk:
            return True
            
        # Пробуем выполнить тестовый запрос
        try:
            vk.users.get(user_ids=[1])
            return True
        except Exception as e:
            logging.warning(f"Ошибка при проверке токена: {e}")
            
        # Если токен недействителен, пытаемся обновить
        try:
            vk_session = VkApi(token=VK_API_TOKEN)
            vk = vk_session.get_api()
            return True
        except Exception as e:
            logging.error(f"Не удалось обновить токен: {e}")
            return False
            
    except Exception as e:
        logging.error(f"Ошибка при обновлении токена: {e}")
        return False

def cleanup_temp_files():
    """Очищает временную директорию от старых файлов"""
    try:
        files_dir = './files'
        if not os.path.exists(files_dir):
            return
            
        current_time = time.time()
        for filename in os.listdir(files_dir):
            file_path = os.path.join(files_dir, filename)
            # Удаляем файлы старше 1 дня (86400 секунд)
            if os.path.isfile(file_path) and current_time - os.path.getmtime(file_path) > 86400:
                try:
                    os.remove(file_path)
                    logging.info(f"Удален старый временный файл: {filename}")
                except Exception as e:
                    logging.error(f"Не удалось удалить временный файл {filename}: {e}")
    except Exception as e:
        logging.error(f"Ошибка при очистке временных файлов: {e}")

def init_supabase():
    """Инициализирует клиент Supabase"""
    global supabase
    
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            logging.info("Supabase успешно инициализирован")
            
            # Функция increment не используется, поэтому не проверяем ее наличие
            logging.info("Инициализация Supabase успешно завершена")
            
            # Проверяем наличие необходимых таблиц
            check_database_structure()
        except Exception as e:
            logging.error(f"Ошибка при инициализации Supabase: {e}")
            supabase = None
    else:
        logging.warning("Не указаны параметры подключения к Supabase")

def check_database_structure():
    """Проверяет структуру базы данных и создает необходимые элементы"""
    if not supabase:
        return
    
    # Проверяем наличие необходимых таблиц
    required_tables = [
        "telegram_channels", 
        "vk_targets", 
        "crosspost_settings",
        "post_info",
        "logs",
    ]
    
    for table in required_tables:
        try:
            # Проверяем каждую таблицу, получая из нее одну запись
            response = supabase.table(table).select("*").limit(1).execute()
            logging.info(f"Таблица {table} существует")
        except Exception as table_error:
            logging.warning(f"Проблема с таблицей {table}: {table_error}")

def init_vk():
    """Инициализирует клиент VK API"""
    global vk, uploader
    
    # Клиенты VK инициализируются динамически при обработке сообщений
    # Токены берутся из базы данных для каждого канала отдельно
    logging.info("VK API клиенты будут инициализированы динамически при получении сообщений")
    vk = None
    uploader = None

def init_telegram():
    """Функция-заглушка для совместимости с кодом"""
    global telegram_client
    # Телеграм клиент не нужен, так как мы используем python-telegram-bot
    telegram_client = None

def log_to_db(user_id, level, message, details=None):
    """Записывает информацию в лог в базе данных"""
    if not supabase:
        return
        
    try:
        # Создаем запись в логе
        log_data = {
            "user_id": user_id,
            "level": level,
            "message": message,
            "details": details,
            "created_at": datetime.datetime.now().isoformat()
        }
        
        # Сохраняем в базу данных
        supabase.table("logs").insert(log_data).execute()
    except Exception as e:
        logging.error(f"Ошибка при записи в лог в базе данных: {e}")
        
# Инициализация при импорте
cleanup_temp_files()