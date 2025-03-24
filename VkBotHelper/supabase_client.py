import logging
from config import supabase
from datetime import datetime

def get_channel_settings_by_id(channel_id):
    """Получает настройки для канала по его ID"""
    try:
        logging.debug(f"Поиск канала с исходным ID: {channel_id}")

        if not supabase:
            logging.error("Отсутствует соединение с Supabase")
            return None

        # Логируем все каналы в базе для отладки
        all_channels = supabase.table("telegram_channels").select("*").execute()
        logging.debug(f"Все каналы в базе: {all_channels.data}")

        # Ищем канал по исходному ID
        channel_response = supabase.table("telegram_channels").select("id,user_id,channel_id,channel_username").eq("channel_id", channel_id).execute()

        if not channel_response.data or len(channel_response.data) == 0:
            # Пробуем преобразовать ID
            if str(channel_id).startswith("-100"):
                converted_id = int(str(channel_id)[4:])
                logging.debug(f"Пробуем преобразованный ID без префикса: {converted_id}")
                channel_response = supabase.table("telegram_channels").select("id,user_id,channel_id,channel_username").eq("channel_id", converted_id).execute()
            else:
                converted_id = int(f"-100{channel_id}")
                logging.debug(f"Пробуем преобразованный ID с префиксом: {converted_id}")
                channel_response = supabase.table("telegram_channels").select("id,user_id,channel_id,channel_username").eq("channel_id", converted_id).execute()

        if not channel_response.data or len(channel_response.data) == 0:
            logging.info(f"Канал с ID {channel_id} не найден после всех проверок")
            return None

        channel_data = channel_response.data[0]
        logging.debug(f"Найден канал: {channel_data}")

        # Получаем настройки кросспостинга
        settings_response = supabase.table("crosspost_settings")\
            .select("id,vk_target_id,post_as_group")\
            .eq("telegram_channel_id", channel_data["id"])\
            .eq("is_active", True)\
            .execute()

        if not settings_response.data or len(settings_response.data) == 0:
            logging.info(f"Настройки кросспостинга для канала ID {channel_id} не найдены")
            return None

        settings_data = settings_response.data[0]

        # Получаем информацию о цели VK
        vk_response = supabase.table("vk_targets")\
            .select("id,target_id,target_name,access_token,refresh_token,expires_at")\
            .eq("id", settings_data["vk_target_id"])\
            .eq("is_active", True)\
            .execute()

        if not vk_response.data or len(vk_response.data) == 0:
            logging.info(f"Цель VK для канала ID {channel_id} не найдена или не активна")
            continue

        vk_data = vk_response.data[0]

        # Формируем настройки с полными данными
        return {
            "user_id": channel_data["user_id"],
            "channel_id": channel_data["channel_id"],
            "channel_username": channel_data.get("channel_username", ""),
            "target_id": vk_data["target_id"],
            "target_name": vk_data.get("target_name", ""),
            "access_token": vk_data["access_token"],
            "refresh_token": vk_data.get("refresh_token"),
            "expires_at": vk_data.get("expires_at"),
            "post_as_group": settings_data.get("post_as_group", 1),
            "settings_id": settings_data["id"],
            "vk_target_id": vk_data["id"]
        }

        logging.info(f"Канал с ID {channel_id} не найден после всех проверок")
        return None
    except Exception as e:
        logging.error(f"Ошибка при получении настроек канала с ID {channel_id}: {e}")
        return None

def log_post(user_id, message_id, post_id):
    """Логирует информацию о кросспостинге в базу данных"""
    try:
        if not supabase:
            logging.error("Отсутствует соединение с Supabase")
            # Запись в файл как запасной вариант
            with open('data.txt', 'a') as f:
                f.write(f'{message_id}:{post_id}\n')
            return False

        # Проверяем, существует ли уже запись для этого сообщения
        check_response = supabase.table("post_info").select("id").eq("telegram_message_id", message_id).execute()

        if check_response.data and len(check_response.data) > 0:
            logging.info(f"Запись для сообщения {message_id} уже существует, обновляем")

            # Обновляем запись
            update_response = supabase.table("post_info").update({
                "vk_post_id": post_id,
                "updated_at": "now()"
            }).eq("telegram_message_id", message_id).execute()

            post_info_id = check_response.data[0]["id"]
        else:
            # Создаем новую запись в post_info
            new_post_info = {
                "telegram_message_id": message_id,
                "vk_post_id": post_id,
                "created_at": "now()",
                "updated_at": "now()",
                "is_edited": False,
                "edit_count": 0
            }

            # Если есть user_id, добавляем его
            if user_id:
                new_post_info["user_id"] = user_id

            post_info_response = supabase.table("post_info").insert(new_post_info).execute()

            if post_info_response.data and len(post_info_response.data) > 0:
                post_info_id = post_info_response.data[0]["id"]
            else:
                logging.error("Не удалось создать запись в post_info")
                return False

        # Создаем запись в posts, если еще не существует
        new_post = {
            "is_active": True,
            "created_at": "now()",
            "updated_at": "now()"
        }

        # Если есть user_id, добавляем его
        if user_id:
            new_post["user_id"] = user_id

        post_response = supabase.table("posts").insert(new_post).execute()

        if post_response.data and len(post_response.data) > 0:
            post_id_db = post_response.data[0]["id"]
        else:
            logging.error("Не удалось создать запись в posts")
            return False

        # Добавляем запись в post_status
        status_data = {
            "post_id": post_id_db,
            "status": "published",
            "created_at": "now()"
        }

        supabase.table("post_status").insert(status_data).execute()

        # Добавляем метаданные поста
        metadata = {
            "post_id": post_id_db,
            "is_edited": False,
            "edit_count": 0,
            "created_at": "now()",
            "updated_at": "now()"
        }

        supabase.table("post_metadata").insert(metadata).execute()

        # Сохраняем связь между post_info и posts в post_content
        content_data = {
            "post_id": post_id_db,
            "telegram_message_id": message_id,
            "vk_post_id": post_id,
            "created_at": "now()"
        }

        supabase.table("post_content").insert(content_data).execute()

        logging.info(f"Успешно сохранена информация о посте {message_id} -> {post_id}")
        return True
    except Exception as e:
        logging.error(f"Ошибка при сохранении информации о посте: {e}")
        # Запись в файл как запасной вариант
        with open('data.txt', 'a') as f:
            f.write(f'{message_id}:{post_id}\n')
        return False

def get_channels():
    """Получает список всех каналов из базы данных"""
    try:
        if not supabase:
            logging.error("Отсутствует соединение с Supabase")
            return []

        response = supabase.table("telegram_channels").select("*").execute()
        return response.data if response.data else []
    except Exception as e:
        logging.error(f"Ошибка при получении списка каналов: {e}")
        return []

def get_vk_targets():
    """Получает список всех целей VK из базы данных"""
    try:
        if not supabase:
            logging.error("Отсутствует соединение с Supabase")
            return []

        response = supabase.table("vk_targets").select("*").execute()
        return response.data if response.data else []
    except Exception as e:
        logging.error(f"Ошибка при получении списка целей VK: {e}")
        return []

def get_crosspost_settings():
    """Получает список всех настроек кросспостинга из базы данных"""
    try:
        if not supabase:
            logging.error("Отсутствует соединение с Supabase")
            return []

        response = supabase.table("crosspost_settings").select("*").execute()
        return response.data if response.data else []
    except Exception as e:
        logging.error(f"Ошибка при получении настроек кросспостинга: {e}")
        return []

def get_logs(limit=100):
    """Получает список логов из базы данных"""
    try:
        if not supabase:
            logging.error("Отсутствует соединение с Supabase")
            return []

        response = supabase.table("logs").select("*").order("created_at", desc=True).limit(limit).execute()
        return response.data if response.data else []
    except Exception as e:
        logging.error(f"Ошибка при получении логов: {e}")
        return []

def add_channel(user_id, channel_id, channel_title, channel_username):
    """Добавляет новый канал в базу данных"""
    try:
        if not supabase:
            logging.error("Отсутствует соединение с Supabase")
            return None

        # Проверяем, существует ли уже канал с таким ID
        check_response = supabase.table("telegram_channels").select("id").eq("channel_id", channel_id).execute()

        if check_response.data and len(check_response.data) > 0:
            logging.info(f"Канал с ID {channel_id} уже существует")
            return check_response.data[0]["id"]

        # Создаем новый канал
        channel_data = {
            "user_id": user_id,
            "channel_id": channel_id,
            "channel_title": channel_title,
            "channel_username": channel_username,
            "is_verified": False,
            "created_at": "now()"
        }

        response = supabase.table("telegram_channels").insert(channel_data).execute()

        if response.data and len(response.data) > 0:
            return response.data[0]["id"]
        else:
            logging.error("Не удалось добавить канал")
            return None
    except Exception as e:
        logging.error(f"Ошибка при добавлении канала: {e}")
        return None

def add_vk_target(user_id, target_id, target_name, access_token, refresh_token=None, expires_at=None):
    """Добавляет новую цель VK в базу данных"""
    try:
        if not supabase:
            logging.error("Отсутствует соединение с Supabase")
            return None

        # Проверяем, существует ли уже цель с таким ID
        check_response = supabase.table("vk_targets").select("id").eq("target_id", target_id).eq("user_id", user_id).execute()

        if check_response.data and len(check_response.data) > 0:
            logging.info(f"Цель VK с ID {target_id} уже существует")

            # Обновляем токены
            update_data = {
                "access_token": access_token,
                "is_active": True
            }

            if refresh_token:
                update_data["refresh_token"] = refresh_token

            if expires_at:
                update_data["expires_at"] = expires_at

            supabase.table("vk_targets").update(update_data).eq("id", check_response.data[0]["id"]).execute()
            return check_response.data[0]["id"]

        # Создаем новую цель
        target_data = {
            "user_id": user_id,
            "target_id": target_id,
            "target_name": target_name,
            "target_type": "group",
            "access_token": access_token,
            "is_active": True,
            "created_at": "now()"
        }

        if refresh_token:
            target_data["refresh_token"] = refresh_token

        if expires_at:
            target_data["expires_at"] = expires_at

        response = supabase.table("vk_targets").insert(target_data).execute()

        if response.data and len(response.data) > 0:
            return response.data[0]["id"]
        else:
            logging.error("Не удалось добавить цель VK")
            return None
    except Exception as e:
        logging.error(f"Ошибка при добавлении цели VK: {e}")
        return None

def add_crosspost_setting(user_id, telegram_channel_id, vk_target_id, post_as_group=1):
    """Добавляет новую настройку кросспостинга в базу данных"""
    try:
        if not supabase:
            logging.error("Отсутствует соединение с Supabase")
            return None

        # Проверяем, существует ли уже настройка для этой пары канал-цель
        check_response = supabase.table("crosspost_settings")\
            .select("id")\
            .eq("telegram_channel_id", telegram_channel_id)\
            .eq("vk_target_id", vk_target_id)\
            .execute()

        if check_response.data and len(check_response.data) > 0:
            logging.info(f"Настройка кросспостинга для канала {telegram_channel_id} и цели {vk_target_id} уже существует")

            # Активируем настройку, если она была деактивирована
            supabase.table("crosspost_settings").update({
                "is_active": True,
                "post_as_group": post_as_group,
                "updated_at": "now()"
            }).eq("id", check_response.data[0]["id"]).execute()

            return check_response.data[0]["id"]

        # Создаем новую настройку
        setting_data = {
            "user_id": user_id,
            "telegram_channel_id": telegram_channel_id,
            "vk_target_id": vk_target_id,
            "post_as_group": post_as_group,
            "is_active": True,
            "created_at": "now()",
            "updated_at": "now()"
        }

        response = supabase.table("crosspost_settings").insert(setting_data).execute()

        if response.data and len(response.data) > 0:
            return response.data[0]["id"]
        else:
            logging.error("Не удалось добавить настройку кросспостинга")
            return None
    except Exception as e:
        logging.error(f"Ошибка при добавлении настройки кросспостинга: {e}")
        return None

def get_post_history(limit=100):
    """Получает историю постов из базы данных"""
    try:
        if not supabase:
            logging.error("Отсутствует соединение с Supabase")
            return []

        response = supabase.table("post_info").select("*").order("created_at", desc=True).limit(limit).execute()
        return response.data if response.data else []
    except Exception as e:
        logging.error(f"Ошибка при получении истории постов: {e}")
        return []