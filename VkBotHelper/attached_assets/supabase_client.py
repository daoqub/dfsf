import logging
from config import supabase
from datetime import datetime

def get_channel_settings_by_id(channel_id):
    """Получает настройки для канала по его ID"""
    try:
        logging.debug(f"Поиск канала с исходным ID: {channel_id}")
        
        # Логируем все каналы в базе для отладки
        all_channels = supabase.table("telegram_channels").select("*").execute()
        logging.debug(f"Все каналы в базе: {all_channels.data}")
        
        # Ищем канал по исходному ID
        channel_response = supabase.table("telegram_channels").select("id,user_id,channel_username").eq("channel_id", channel_id).execute()
        
        if not channel_response.data or len(channel_response.data) == 0:
            # Пробуем преобразовать ID
            if str(channel_id).startswith("-100"):
                converted_id = int(str(channel_id)[4:])
                logging.debug(f"Пробуем преобразованный ID без префикса: {converted_id}")
                channel_response = supabase.table("telegram_channels").select("id,user_id,channel_username").eq("channel_id", converted_id).execute()
            else:
                converted_id = int(f"-100{channel_id}")
                logging.debug(f"Пробуем преобразованный ID с префиксом: {converted_id}")
                channel_response = supabase.table("telegram_channels").select("id,user_id,channel_username").eq("channel_id", converted_id).execute()
        
        if not channel_response.data or len(channel_response.data) == 0:
            logging.info(f"Канал с ID {channel_id} не найден после всех проверок")
            return None
            
        channel_data = channel_response.data[0]
        logging.debug(f"Найден канал: {channel_data}")
        
        # Получаем настройки кросспостинга
        settings_response = supabase.table("crosspost_settings")\
            .select("vk_target_id,post_as_group")\
            .eq("telegram_channel_id", channel_data["id"])\
            .eq("is_active", True)\
            .execute()
            
        if not settings_response.data or len(settings_response.data) == 0:
            logging.info(f"Настройки кросспостинга для канала ID {channel_id} не найдены")
            return None
            
        settings_data = settings_response.data[0]
        
        # Получаем информацию о цели VK
        vk_response = supabase.table("vk_targets")\
            .select("target_id,access_token,refresh_token,expires_at")\
            .eq("id", settings_data["vk_target_id"])\
            .eq("is_active", True)\
            .execute()
            
        if not vk_response.data or len(vk_response.data) == 0:
            logging.info(f"Цель VK для канала ID {channel_id} не найдена или не активна")
            return None
            
        vk_data = vk_response.data[0]
        
        # Формируем настройки
        return {
            "user_id": channel_data["user_id"],
            "channel_username": channel_data.get("channel_username", ""),
            "target_id": vk_data["target_id"],
            "access_token": vk_data["access_token"],
            "refresh_token": vk_data["refresh_token"],
            "expires_at": vk_data["expires_at"],
            "post_as_group": settings_data.get("post_as_group", 1)  # По умолчанию публикуем от имени группы
        }
    except Exception as e:
        logging.error(f"Ошибка при получении настроек канала с ID {channel_id}: {e}")
        return None

def log_post(user_id, message_id, post_id):
    """Логирует информацию о кросспостинге в базу данных"""
    try:
        from config import supabase, telegram_client
        
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
            # Получаем информацию о канале для добавления в post_info
            channel_id = None
            channel_username = None
            
            if message_id:
                try:
                    # Пытаемся получить информацию о канале из сообщения
                    message = telegram_client.get_messages(entity=None, ids=message_id)
                    if message and message.chat:
                        if hasattr(message.chat, 'username') and message.chat.username:
                            channel_username = message.chat.username
                        if hasattr(message.chat, 'id') and message.chat.id:
                            channel_id_raw = message.chat.id
                            
                            # Находим запись в telegram_channels или создаем новую
                            channel_query = supabase.table("telegram_channels").select("id").eq("channel_id", channel_id_raw).execute()
                            
                            if channel_query.data and len(channel_query.data) > 0:
                                channel_id = channel_query.data[0]["id"]
                            else:
                                # Создаем новую запись канала
                                new_channel = {
                                    "channel_id": channel_id_raw,
                                    "is_active": True
                                }
                                
                                if channel_username:
                                    new_channel["channel_username"] = channel_username
                                    
                                channel_response = supabase.table("telegram_channels").insert(new_channel).execute()
                                if channel_response.data and len(channel_response.data) > 0:
                                    channel_id = channel_response.data[0]["id"]
                except Exception as e:
                    logging.error(f"Не удалось получить информацию о канале: {e}")
            
            # Создаем новую запись в post_info
            new_post_info = {
                "telegram_message_id": message_id,
                "vk_post_id": post_id,
                "created_at": "now()",
                "updated_at": "now()",
                "is_edited": False,
                "edit_count": 0
            }
            
            # Добавляем информацию о канале, если она есть
            if channel_id:
                new_post_info["telegram_channel_id"] = channel_id
            if channel_username:
                new_post_info["channel_username"] = channel_username
                
            # Если есть user_id, добавляем его
            if user_id:
                new_post_info["user_id"] = user_id
                
            post_info_response = supabase.table("post_info").insert(new_post_info).execute()
            
            if post_info_response.data and len(post_info_response.data) > 0:
                post_info_id = post_info_response.data[0]["id"]
            else:
                logging.error("Не удалось создать запись в post_info")
                return
        
        # Проверяем наличие поста в таблице posts
        post_id_db = None
        
        # Ищем пост по telegram_channel_id, если есть
        if channel_id:
            posts_query = supabase.table("posts").select("id").eq("telegram_channel_id", channel_id).execute()
            if posts_query.data and len(posts_query.data) > 0:
                post_id_db = posts_query.data[0]["id"]
        
        # Если не нашли по каналу, создаем новую запись в posts
        if not post_id_db:
            new_post = {
                "is_active": True,
                "created_at": "now()",
                "updated_at": "now()"
            }
            
            # Если есть channel_id, добавляем его
            if channel_id:
                new_post["telegram_channel_id"] = channel_id
                
            # Если есть user_id, добавляем его
            if user_id:
                new_post["user_id"] = user_id
                
            post_response = supabase.table("posts").insert(new_post).execute()
            
            if post_response.data and len(post_response.data) > 0:
                post_id_db = post_response.data[0]["id"]
            else:
                logging.error("Не удалось создать запись в posts")
                return
        
        # Добавляем запись в post_status
        status_data = {
            "post_id": post_id_db,
            "status": "published",
            "created_at": "now()"
        }
        
        supabase.table("post_status").insert(status_data).execute()
        
        # Добавляем метаданные поста
        metadata_query = supabase.table("post_metadata").select("id").eq("post_id", post_id_db).execute()
        
        if metadata_query.data and len(metadata_query.data) > 0:
            # Обновляем существующую запись
            supabase.table("post_metadata").update({
                "updated_at": "now()"
            }).eq("post_id", post_id_db).execute()
        else:
            # Создаем новую запись метаданных
            metadata = {
                "post_id": post_id_db,
                "is_edited": False,
                "edit_count": 0,
                "created_at": "now()",
                "updated_at": "now()"
            }
            
            supabase.table("post_metadata").insert(metadata).execute()
        
        # Сохраняем связь между post_info и posts в post_content, если это еще не сделано
        content_query = supabase.table("post_content").select("id").eq("telegram_message_id", message_id).execute()
        
        if not content_query.data or len(content_query.data) == 0:
            # Создаем запись с базовыми данными, текст может быть добавлен позже
            content_data = {
                "post_id": post_id_db,
                "telegram_message_id": message_id,
                "vk_post_id": post_id
            }
            
            supabase.table("post_content").insert(content_data).execute()
            
        logging.info(f"Успешно сохранена информация о посте {message_id} -> {post_id}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении информации о посте: {e}")

def get_channel_settings(channel_id):
    """Получает настройки для канала по его ID"""
    try:
        from config import supabase
        
        # Находим канал по ID
        channel_query = supabase.table("telegram_channels").select("id").eq("channel_id", channel_id).execute()
        
        if not channel_query.data or len(channel_query.data) == 0:
            logging.warning(f"Канал с ID {channel_id} не найден в базе")
            return None
        
        channel_db_id = channel_query.data[0]["id"]
        
        # Получаем настройки кросспостинга для этого канала
        settings_query = supabase.table("crosspost_settings").select("*").eq("telegram_channel_id", channel_db_id).eq("is_active", True).execute()
        
        if not settings_query.data or len(settings_query.data) == 0:
            logging.warning(f"Настройки для канала {channel_id} не найдены")
            return None
        
        return settings_query.data
    except Exception as e:
        logging.error(f"Ошибка при получении настроек канала: {e}")
        return None