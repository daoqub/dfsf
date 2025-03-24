import logging
import os
from config import vk
from typing import Optional, Dict

def get_entry(message_id: int) -> Optional[int]:
    """Получает ID поста VK по ID сообщения Telegram"""
    try:
        from config import supabase
        
        if not supabase:
            # Чтение из файла как запасной вариант
            with open('data.txt', 'r') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if len(parts) == 2 and int(parts[0]) == message_id:
                        return int(parts[1])
            raise KeyError(f"Не найдено соответствие для сообщения {message_id}")
        
        # Получаем данные из Supabase из таблицы post_info
        response = supabase.table("post_info").select("vk_post_id").eq("telegram_message_id", message_id).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]["vk_post_id"]
        else:
            raise KeyError(f"Не найдено соответствие для сообщения {message_id}")
    except Exception as e:
        logging.error(f"Ошибка при получении соответствия ID: {e}")
        # Чтение из файла как запасной вариант
        with open('data.txt', 'r') as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) == 2 and int(parts[0]) == message_id:
                    return int(parts[1])
        raise KeyError(f"Не найдено соответствие для сообщения {message_id}")

def add_entry(message_id: int, post_id: int, user_id: Optional[str] = None) -> bool:
    """Сохраняет соответствие ID сообщения Telegram и поста VK в базе данных"""
    try:
        from config import supabase
        
        if not supabase:
            # Запись в файл как запасной вариант
            with open('data.txt', 'a') as f:
                f.write(f'{message_id}:{post_id}\n')
            return True
        
        from supabase_client import log_post
        
        # Используем переданный user_id
        log_post(user_id, message_id, post_id)
        return True
    except Exception as e:
        logging.error(f"Не удалось сохранить соответствие ID: {e}")
        # Запись в файл как запасной вариант
        with open('data.txt', 'a') as f:
            f.write(f'{message_id}:{post_id}\n')
        return False

def edit_vk_post(post_id: int, new_text: str, message_id: int) -> bool:
    """Редактирует существующий пост VK"""
    try:
        from config import vk, VK_GROUP_ID
        
        # Получаем оригинальный пост
        old_post = vk.wall.getById(posts=f'-{VK_GROUP_ID}_{post_id}')[0]
        attachments = [f'{attachment["type"]}{attachment[attachment["type"]]["owner_id"]}_{attachment[attachment["type"]]["id"]}' for attachment in old_post.get('attachments', [])]
        
        # Получаем канал для формирования ссылки
        response = vk.wall.getById(posts=f'-{VK_GROUP_ID}_{post_id}', copy_history_depth=0)
        if not response:
            logging.error(f"Не удалось получить информацию о посте {post_id}")
            return False
            
        # Формируем ссылку на источник
        source_link = get_source_link_for_edit(message_id)
        
        # Редактируем пост
        vk.wall.edit(
            message=new_text,
            post_id=post_id,
            from_group=1,
            owner_id=f'-{VK_GROUP_ID}',
            copyright=source_link,
            attachments=attachments
        )
        
        # Обновляем информацию в базе данных
        try:
            from config import supabase
            
            # Получаем информацию о посте из post_info
            post_info_query = supabase.table("post_info").select("id,telegram_channel_id").eq("telegram_message_id", message_id).execute()
            
            if post_info_query.data and len(post_info_query.data) > 0:
                post_info = post_info_query.data[0]
                post_info_id = post_info["id"]
                
                # Обновляем запись о посте в post_info
                supabase.table("post_info").update({
                    "is_edited": True,
                    "edit_count": supabase.rpc("increment", {"x": 1})
                }).eq("id", post_info_id).execute()
                
                # Ищем связанный пост в таблице posts
                posts_query = None
                
                if "telegram_channel_id" in post_info and post_info["telegram_channel_id"]:
                    # Ищем по ID канала, так как это более надежный способ связи
                    posts_query = supabase.table("posts").select("id").eq("telegram_channel_id", post_info["telegram_channel_id"]).execute()
                
                if not posts_query or not posts_query.data or len(posts_query.data) == 0:
                    # Ищем через post_content, так как там может быть связь с ID поста
                    content_query = supabase.table("post_content").select("post_id").eq("telegram_message_id", message_id).execute()
                    if content_query.data and len(content_query.data) > 0:
                        post_id_db = content_query.data[0]["post_id"]
                    else:
                        # Если не нашли, создаем новую запись в posts
                        new_post_response = supabase.table("posts").insert({
                            "is_active": True,
                            "updated_at": "now()"
                        }).execute()
                        post_id_db = new_post_response.data[0]["id"] if new_post_response.data else None
                else:
                    post_id_db = posts_query.data[0]["id"]
                
                # Если нашли ID поста, обновляем связанные таблицы
                if post_id_db:
                    # Обновляем статус в post_status
                    supabase.table("post_status").insert({
                        "post_id": post_id_db,
                        "status": "edited",
                        "created_at": "now()"
                    }).execute()
                    
                    # Обновляем post_metadata или создаем новую запись
                    metadata_query = supabase.table("post_metadata").select("id").eq("post_id", post_id_db).execute()
                    if metadata_query.data and len(metadata_query.data) > 0:
                        # Обновляем существующую запись
                        supabase.table("post_metadata").update({
                            "is_edited": True,
                            "edit_count": supabase.rpc("increment", {"x": 1}),
                            "updated_at": "now()"
                        }).eq("post_id", post_id_db).execute()
                    else:
                        # Создаем новую запись метаданных
                        supabase.table("post_metadata").insert({
                            "post_id": post_id_db,
                            "is_edited": True,
                            "edit_count": 1,
                            "created_at": "now()",
                            "updated_at": "now()"
                        }).execute()
                    
                    # Проверяем, есть ли запись в post_content
                    content_query = supabase.table("post_content").select("id").eq("post_id", post_id_db).execute()
                    if not content_query.data or len(content_query.data) == 0:
                        # Создаем запись с текстом поста
                        supabase.table("post_content").insert({
                            "post_id": post_id_db,
                            "telegram_message_id": message_id,
                            "vk_post_id": post_id,
                            "content": new_text
                        }).execute()
        except Exception as db_error:
            logging.error(f"Ошибка при обновлении информации о посте: {db_error}")
        
        return True
    except Exception as e:
        logging.error(f'Error while editing VK post: {e}')
        return False

def get_source_link_for_edit(message_id: int) -> Optional[str]:
    """Создает ссылку на оригинальный пост в Telegram для редактирования"""
    try:
        from config import supabase
        
        # Получаем информацию о посте из базы данных
        response = supabase.table("post_info")\
            .select("telegram_message_id,telegram_channel_id,channel_username")\
            .eq("telegram_message_id", message_id)\
            .execute()
            
        if not response.data or len(response.data) == 0:
            # Запасной вариант - формируем ссылку на сообщение без канала
            return f'https://t.me/{message_id}'
        
        post_data = response.data[0]
        
        # Если имеем username канала напрямую из post_info
        if post_data.get("channel_username"):
            return f'https://t.me/{post_data["channel_username"]}/{message_id}'
            
        # Если нет username, но есть ID канала, пробуем получить дополнительную информацию
        if post_data.get("telegram_channel_id"):
            channel_response = supabase.table("telegram_channels")\
                .select("channel_id,channel_username")\
                .eq("id", post_data["telegram_channel_id"])\
                .execute()
                
            if channel_response.data and len(channel_response.data) > 0:
                channel = channel_response.data[0]
                
                if channel.get("channel_username"):
                    return f'https://t.me/{channel["channel_username"]}/{message_id}'
                else:
                    clean_id = str(channel["channel_id"])
                    if clean_id.startswith("-100"):
                        clean_id = clean_id[4:]
                    return f'https://t.me/c/{clean_id}/{message_id}'
                    
        # Если не смогли получить информацию о канале
        return f'https://t.me/{message_id}'
    except Exception as e:
        logging.error(f"Ошибка при формировании ссылки: {e}")
        return f'https://t.me/{message_id}'