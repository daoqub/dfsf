import logging
import os
import random
import asyncio
from typing import Dict, List
from datetime import datetime

from telegram import Update
from telegram.ext import CallbackContext
from vk_api import VkApi
from vk_api.upload import VkUpload
from PIL import Image

from vk_client import edit_vk_post, get_entry, add_entry, get_source_link_for_edit
from config import refresh_token_if_needed, format_owner_id, log_to_db
from supabase_client import get_channel_settings_by_id
import config

# Константы
MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100 МБ в байтах

# Словарь для хранения медиагрупп
media_groups: Dict[str, List[Update]] = {}

def is_user_forward(message):
    """Проверяет, является ли сообщение пересланным от пользователя"""
    if hasattr(message, 'forward_from') and message.forward_from:
        return True
    if hasattr(message, 'forward_from_chat') and message.forward_from_chat:
        if hasattr(message.forward_from_chat, 'type') and message.forward_from_chat.type == 'channel':
            return False
        return True
    return False

async def download_file_with_retries(file, path, max_retries=3):
    """Загружает файл с повторами в случае ошибки"""
    retries = 0
    while retries < max_retries:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            await file.download_to_drive(path)
            return True
        except Exception as e:
            logging.error(f"Ошибка при загрузке файла (попытка {retries+1}/{max_retries}): {e}")
            retries += 1
            await asyncio.sleep(1)
    logging.error(f"Не удалось загрузить файл после {max_retries} попыток")
    return False

def get_source_link(message):
    """Создает ссылку на канал и сообщение для указания источника"""
    chat = message.chat if hasattr(message, 'chat') else None
    if not chat:
        return None
        
    chat_id = chat.id
    msg_id = message.message_id if hasattr(message, 'message_id') else None
    
    if not msg_id:
        return None
        
    if chat.username:
        return f'https://t.me/{chat.username}/{msg_id}'
    else:
        # Для приватных каналов используем формат с ID канала
        clean_id = str(chat_id)
        if clean_id.startswith("-100"):
            clean_id = clean_id[4:]
        return f'https://t.me/c/{clean_id}/{msg_id}'

async def handle_media_group(update: Update, context: CallbackContext):
    """Обрабатывает группы медиафайлов"""
    try:
        message = update.channel_post
        if not message or not message.media_group_id:
            return
            
        # Проверяем, является ли сообщение перепостом от пользователя
        if is_user_forward(message):
            logging.info("Пропуск перепоста от пользователя")
            return
            
        # Добавляем сообщение в группу
        group_id = message.media_group_id
        if group_id not in media_groups:
            media_groups[group_id] = []
        media_groups[group_id].append(message)
        
        # Ждем остальные сообщения из группы
        await asyncio.sleep(2)
        
        # Если группа уже обрабатывалась, пропускаем
        if group_id not in media_groups:
            return
            
        messages = media_groups[group_id]
        del media_groups[group_id]
        
        # Получаем настройки канала
        channel_id = message.chat.id
        channel_username = message.chat.username
        
        settings = get_channel_settings_by_id(channel_id)
        if not settings:
            logging.info(f"Сообщение из неотслеживаемого канала: ID={channel_id}, username={channel_username}")
            return
            
        config.VK_API_TOKEN = settings["access_token"]
        config.VK_GROUP_ID = settings["target_id"]
        post_as_group = settings.get("post_as_group", 1)
        
        if not refresh_token_if_needed():
            logging.error(f"Не удалось обновить токен для канала ID={channel_id}")
            return
            
        vk_session = VkApi(token=config.VK_API_TOKEN)
        config.vk = vk_session.get_api()
        config.uploader = VkUpload(config.vk)
        
        random_number = random.randint(1000000, 9999999)
        photo_list, video_list, doc_list, audio_list = [], [], [], []
        text = None
        
        # Проверка на большие видео
        has_large_videos = False
        large_video_count = 0
        
        for msg in messages:
            if msg.caption and not text:
                text = msg.caption
                
            if msg.photo:
                path = f'./files/photo_{random_number}_{len(photo_list)}.jpg'
                if await download_file_with_retries(msg.photo[-1].get_file(), path):
                    photo_list.append(path)
                    
            elif msg.video:
                if msg.video.file_size > MAX_VIDEO_SIZE:
                    has_large_videos = True
                    large_video_count += 1
                else:
                    path = f'./files/video_{random_number}_{len(video_list)}.mp4'
                    if await download_file_with_retries(msg.video.get_file(), path):
                        video_list.append(path)
                        
            elif msg.document:
                path = f'./files/doc_{random_number}_{len(doc_list)}_{msg.document.file_name}'
                if await download_file_with_retries(msg.document.get_file(), path):
                    doc_list.append(path)
                    
            elif msg.audio:
                path = f'./files/audio_{random_number}_{len(audio_list)}.mp3'
                if hasattr(msg.audio, 'file_name') and msg.audio.file_name:
                    path = f'./files/audio_{random_number}_{len(audio_list)}_{msg.audio.file_name}'
                if await download_file_with_retries(msg.audio.get_file(), path):
                    audio_list.append(path)
                    
        source_link = get_source_link(messages[0])
        post_text = text if text else ''
        
        if has_large_videos:
            post_text += f"\n\n{large_video_count} видео {'доступны' if large_video_count > 1 else 'доступно'} по ссылке: {source_link}"
            
        # Загружаем файлы в ВК
        attachments = []
        
        for path in photo_list:
            try:
                photo = config.uploader.photo_wall(path)[0]
                attachments.append(f'photo{photo["owner_id"]}_{photo["id"]}')
            except Exception as e:
                logging.error(f"Ошибка при загрузке фото {path}: {e}")
            
        for path in video_list:
            try:
                video = config.uploader.video(path, name=os.path.basename(path))
                attachments.append(f'video{video["owner_id"]}_{video["video_id"]}')
            except Exception as e:
                logging.error(f"Ошибка при загрузке видео {path}: {e}")
            
        for path in doc_list:
            try:
                doc = config.uploader.document(path, title=os.path.basename(path))
                attachments.append(f'doc{doc["doc"]["owner_id"]}_{doc["doc"]["id"]}')
            except Exception as e:
                logging.error(f"Ошибка при загрузке документа {path}: {e}")
            
        for path in audio_list:
            try:
                audio = config.uploader.audio(path, title=os.path.basename(path))
                attachments.append(f'audio{audio["owner_id"]}_{audio["id"]}')
            except Exception as e:
                logging.error(f"Ошибка при загрузке аудио {path}: {e}")
            
        try:
            # Публикуем пост
            owner_id = format_owner_id(config.VK_GROUP_ID)
            response = await asyncio.to_thread(
                config.vk.wall.post,
                owner_id=owner_id,
                from_group=post_as_group,
                message=post_text,
                attachments=','.join(attachments) if attachments else '',
                copyright=source_link
            )
            
            if response and 'post_id' in response:
                add_entry(messages[0].message_id, response['post_id'], settings['user_id'])
                log_to_db(
                    settings['user_id'], 
                    "info", 
                    f"Опубликован медиа-пост из канала {channel_username or channel_id} в группу {settings.get('target_name') or config.VK_GROUP_ID}",
                    f"Сообщение: {messages[0].message_id}, Пост: {response['post_id']}"
                )
        except Exception as post_error:
            logging.error(f"Ошибка при публикации поста: {post_error}")
            log_to_db(
                settings['user_id'],
                "error",
                f"Ошибка при публикации медиа-поста из канала {channel_username or channel_id}",
                str(post_error)
            )
                
        # Удаляем временные файлы
        for path in photo_list + video_list + doc_list + audio_list:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logging.error(f"Ошибка при удалении файла {path}: {e}")
                
    except Exception as e:
        logging.error(f"Ошибка при обработке медиагруппы: {e}")

async def handle_photo_video(update: Update, context: CallbackContext):
    """Обрабатывает одиночные фото или видео"""
    try:
        message = update.channel_post
        if not message:
            return
            
        # Проверяем, является ли сообщение перепостом от пользователя
        if is_user_forward(message):
            logging.info("Пропуск перепоста от пользователя")
            return
            
        # Проверяем, является ли сообщение частью медиагруппы
        if hasattr(message, 'media_group_id') and message.media_group_id:
            return  # Медиагруппы обрабатываются отдельно
            
        channel_id = message.chat.id
        channel_username = message.chat.username
        
        settings = get_channel_settings_by_id(channel_id)
        if not settings:
            logging.info(f"Сообщение из неотслеживаемого канала: ID={channel_id}, username={channel_username}")
            return
            
        config.VK_API_TOKEN = settings["access_token"]
        config.VK_GROUP_ID = settings["target_id"]
        post_as_group = settings.get("post_as_group", 1)
        
        if not refresh_token_if_needed():
            logging.error(f"Не удалось обновить токен для канала ID={channel_id}")
            return
            
        vk_session = VkApi(token=config.VK_API_TOKEN)
        config.vk = vk_session.get_api()
        config.uploader = VkUpload(config.vk)
        
        text = message.caption if message.caption else ''
        source_link = get_source_link(message)
        owner_id = format_owner_id(config.VK_GROUP_ID)
        
        if message.photo:
            random_number = random.randint(1000000, 9999999)
            path = f'./files/photo_{random_number}.jpg'
            
            if await download_file_with_retries(message.photo[-1].get_file(), path):
                try:
                    photo = config.uploader.photo_wall(path)[0]
                    
                    response = await asyncio.to_thread(
                        config.vk.wall.post,
                        owner_id=owner_id,
                        from_group=post_as_group,
                        message=text,
                        attachments=f'photo{photo["owner_id"]}_{photo["id"]}',
                        copyright=source_link
                    )
                    
                    if response and 'post_id' in response:
                        add_entry(message.message_id, response['post_id'], settings['user_id'])
                        log_to_db(
                            settings['user_id'], 
                            "info", 
                            f"Опубликовано фото из канала {channel_username or channel_id} в группу {settings.get('target_name') or config.VK_GROUP_ID}",
                            f"Сообщение: {message.message_id}, Пост: {response['post_id']}"
                        )
                except Exception as e:
                    logging.error(f"Ошибка при публикации фото: {e}")
                    log_to_db(
                        settings['user_id'],
                        "error",
                        f"Ошибка при публикации фото из канала {channel_username or channel_id}",
                        str(e)
                    )
                finally:
                    if os.path.exists(path):
                        os.remove(path)
                
        elif message.video:
            if message.video.file_size > MAX_VIDEO_SIZE:
                post_text = f"{text}\n\nВидео доступно по ссылке: {source_link}"
                
                try:
                    response = await asyncio.to_thread(
                        config.vk.wall.post,
                        owner_id=owner_id,
                        from_group=post_as_group,
                        message=post_text,
                        copyright=source_link
                    )
                    
                    if response and 'post_id' in response:
                        add_entry(message.message_id, response['post_id'], settings['user_id'])
                        log_to_db(
                            settings['user_id'], 
                            "info", 
                            f"Опубликована ссылка на видео из канала {channel_username or channel_id} в группу {settings.get('target_name') or config.VK_GROUP_ID}",
                            f"Сообщение: {message.message_id}, Пост: {response['post_id']}"
                        )
                except Exception as e:
                    logging.error(f"Ошибка при публикации ссылки на видео: {e}")
                    log_to_db(
                        settings['user_id'],
                        "error",
                        f"Ошибка при публикации ссылки на видео из канала {channel_username or channel_id}",
                        str(e)
                    )
            else:
                random_number = random.randint(1000000, 9999999)
                path = f'./files/video_{random_number}.mp4'
                
                if await download_file_with_retries(message.video.get_file(), path):
                    try:
                        video_name = f"Видео {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        video = config.uploader.video(path, name=video_name)
                        
                        response = await asyncio.to_thread(
                            config.vk.wall.post,
                            owner_id=owner_id,
                            from_group=post_as_group,
                            message=text,
                            attachments=f'video{video["owner_id"]}_{video["video_id"]}',
                            copyright=source_link
                        )
                        
                        if response and 'post_id' in response:
                            add_entry(message.message_id, response['post_id'], settings['user_id'])
                            log_to_db(
                                settings['user_id'], 
                                "info", 
                                f"Опубликовано видео из канала {channel_username or channel_id} в группу {settings.get('target_name') or config.VK_GROUP_ID}",
                                f"Сообщение: {message.message_id}, Пост: {response['post_id']}"
                            )
                    except Exception as e:
                        logging.error(f"Ошибка при публикации видео: {e}")
                        log_to_db(
                            settings['user_id'],
                            "error",
                            f"Ошибка при публикации видео из канала {channel_username or channel_id}",
                            str(e)
                        )
                    finally:
                        if os.path.exists(path):
                            os.remove(path)
                    
    except Exception as e:
        logging.error(f"Ошибка при обработке фото или видео: {e}")

async def handle_document(update: Update, context: CallbackContext):
    """Обрабатывает документы - обрабатываем только избранные типы файлов"""
    # Пропускаем стикеры, GIF и непонятные типы файлов
    message = update.channel_post
    if not message or not message.document:
        return
        
    # Получаем MIME тип документа
    mime_type = message.document.mime_type.lower() if message.document.mime_type else ""
    file_name = message.document.file_name.lower() if message.document.file_name else ""
    
    # Пропускаем стикеры, GIF и непонятные типы файлов
    if "image/gif" in mime_type or "tgs" in file_name or "webp" in file_name:
        logging.info(f"Пропуск GIF/стикера/анимации: {mime_type}, {file_name}")
        return
    try:
        message = update.channel_post
        if not message or not message.document:
            return
            
        # Проверяем, является ли сообщение перепостом от пользователя
        if is_user_forward(message):
            logging.info("Пропуск перепоста от пользователя")
            return
            
        # Проверяем, является ли сообщение частью медиагруппы
        if hasattr(message, 'media_group_id') and message.media_group_id:
            return  # Медиагруппы обрабатываются отдельно
            
        channel_id = message.chat.id
        channel_username = message.chat.username
        
        settings = get_channel_settings_by_id(channel_id)
        if not settings:
            logging.info(f"Сообщение из неотслеживаемого канала: ID={channel_id}, username={channel_username}")
            return
            
        config.VK_API_TOKEN = settings["access_token"]
        config.VK_GROUP_ID = settings["target_id"]
        post_as_group = settings.get("post_as_group", 1)
        
        if not refresh_token_if_needed():
            logging.error(f"Не удалось обновить токен для канала ID={channel_id}")
            return
            
        vk_session = VkApi(token=config.VK_API_TOKEN)
        config.vk = vk_session.get_api()
        config.uploader = VkUpload(config.vk)
        
        text = message.caption if message.caption else ''
        source_link = get_source_link(message)
        owner_id = format_owner_id(config.VK_GROUP_ID)
        
        random_number = random.randint(1000000, 9999999)
        file_name = message.document.file_name if message.document.file_name else f"document_{random_number}"
        path = f'./files/doc_{random_number}_{file_name}'
        
        if await download_file_with_retries(message.document.get_file(), path):
            try:
                doc = config.uploader.document(path, title=file_name)
                
                response = await asyncio.to_thread(
                    config.vk.wall.post,
                    owner_id=owner_id,
                    from_group=post_as_group,
                    message=text,
                    attachments=f'doc{doc["doc"]["owner_id"]}_{doc["doc"]["id"]}',
                    copyright=source_link
                )
                
                if response and 'post_id' in response:
                    add_entry(message.message_id, response['post_id'], settings['user_id'])
                    log_to_db(
                        settings['user_id'], 
                        "info", 
                        f"Опубликован документ из канала {channel_username or channel_id} в группу {settings.get('target_name') or config.VK_GROUP_ID}",
                        f"Сообщение: {message.message_id}, Пост: {response['post_id']}"
                    )
            except Exception as e:
                logging.error(f"Ошибка при публикации документа: {e}")
                log_to_db(
                    settings['user_id'],
                    "error",
                    f"Ошибка при публикации документа из канала {channel_username or channel_id}",
                    str(e)
                )
            finally:
                if os.path.exists(path):
                    os.remove(path)
                
    except Exception as e:
        logging.error(f"Ошибка при обработке документа: {e}")

async def handle_audio(update: Update, context: CallbackContext):
    """Обрабатывает аудиофайлы"""
    try:
        message = update.channel_post
        if not message or not message.audio:
            return
            
        # Проверяем, является ли сообщение перепостом от пользователя
        if is_user_forward(message):
            logging.info("Пропуск перепоста от пользователя")
            return
            
        # Проверяем, является ли сообщение частью медиагруппы
        if hasattr(message, 'media_group_id') and message.media_group_id:
            return  # Медиагруппы обрабатываются отдельно
            
        channel_id = message.chat.id
        channel_username = message.chat.username
        
        settings = get_channel_settings_by_id(channel_id)
        if not settings:
            logging.info(f"Сообщение из неотслеживаемого канала: ID={channel_id}, username={channel_username}")
            return
            
        config.VK_API_TOKEN = settings["access_token"]
        config.VK_GROUP_ID = settings["target_id"]
        post_as_group = settings.get("post_as_group", 1)
        
        if not refresh_token_if_needed():
            logging.error(f"Не удалось обновить токен для канала ID={channel_id}")
            return
            
        vk_session = VkApi(token=config.VK_API_TOKEN)
        config.vk = vk_session.get_api()
        config.uploader = VkUpload(config.vk)
        
        text = message.caption if message.caption else ''
        source_link = get_source_link(message)
        owner_id = format_owner_id(config.VK_GROUP_ID)
        
        random_number = random.randint(1000000, 9999999)
        audio_title = ""
        
        if message.audio.title:
            audio_title = message.audio.title
            if message.audio.performer:
                audio_title = f"{message.audio.performer} - {audio_title}"
        elif message.audio.file_name:
            audio_title = message.audio.file_name
        else:
            audio_title = f"audio_{random_number}"
            
        path = f'./files/audio_{random_number}.mp3'
        
        if await download_file_with_retries(message.audio.get_file(), path):
            try:
                audio = config.uploader.audio(path, title=audio_title)
                
                response = await asyncio.to_thread(
                    config.vk.wall.post,
                    owner_id=owner_id,
                    from_group=post_as_group,
                    message=text,
                    attachments=f'audio{audio["owner_id"]}_{audio["id"]}',
                    copyright=source_link
                )
                
                if response and 'post_id' in response:
                    add_entry(message.message_id, response['post_id'], settings['user_id'])
                    log_to_db(
                        settings['user_id'], 
                        "info", 
                        f"Опубликован аудиофайл из канала {channel_username or channel_id} в группу {settings.get('target_name') or config.VK_GROUP_ID}",
                        f"Сообщение: {message.message_id}, Пост: {response['post_id']}"
                    )
            except Exception as e:
                logging.error(f"Ошибка при публикации аудио: {e}")
                log_to_db(
                    settings['user_id'],
                    "error",
                    f"Ошибка при публикации аудио из канала {channel_username or channel_id}",
                    str(e)
                )
            finally:
                if os.path.exists(path):
                    os.remove(path)
                
    except Exception as e:
        logging.error(f"Ошибка при обработке аудио: {e}")

async def handle_text(update: Update, context: CallbackContext):
    """Обрабатывает текстовые сообщения"""
    try:
        message = update.channel_post
        if not message or not message.text:
            return
            
        # Проверяем, является ли сообщение перепостом от пользователя
        if is_user_forward(message):
            logging.info("Пропуск перепоста от пользователя")
            return
            
        channel_id = message.chat.id
        channel_username = message.chat.username
        
        settings = get_channel_settings_by_id(channel_id)
        if not settings:
            logging.info(f"Сообщение из неотслеживаемого канала: ID={channel_id}, username={channel_username}")
            return
            
        config.VK_API_TOKEN = settings["access_token"]
        config.VK_GROUP_ID = settings["target_id"]
        post_as_group = settings.get("post_as_group", 1)
        
        if not refresh_token_if_needed():
            logging.error(f"Не удалось обновить токен для канала ID={channel_id}")
            return
            
        vk_session = VkApi(token=config.VK_API_TOKEN)
        config.vk = vk_session.get_api()
        
        source_link = get_source_link(message)
        owner_id = format_owner_id(config.VK_GROUP_ID)
        
        try:
            response = await asyncio.to_thread(
                config.vk.wall.post,
                owner_id=owner_id,
                from_group=post_as_group,
                message=message.text,
                copyright=source_link
            )
            
            if response and 'post_id' in response:
                add_entry(message.message_id, response['post_id'], settings['user_id'])
                log_to_db(
                    settings['user_id'], 
                    "info", 
                    f"Опубликовано текстовое сообщение из канала {channel_username or channel_id} в группу {settings.get('target_name') or config.VK_GROUP_ID}",
                    f"Сообщение: {message.message_id}, Пост: {response['post_id']}"
                )
        except Exception as e:
            logging.error(f"Ошибка при публикации текстового сообщения: {e}")
            log_to_db(
                settings['user_id'],
                "error",
                f"Ошибка при публикации текстового сообщения из канала {channel_username or channel_id}",
                str(e)
            )
                
    except Exception as e:
        logging.error(f"Ошибка при обработке текстового сообщения: {e}")

async def handle_edited_message(update: Update, context: CallbackContext):
    """Обрабатывает отредактированные сообщения"""
    try:
        message = update.edited_channel_post
        if not message:
            return
            
        # Проверяем, является ли сообщение перепостом от пользователя
        if is_user_forward(message):
            logging.info("Пропуск перепоста от пользователя")
            return
            
        channel_id = message.chat.id
        channel_username = message.chat.username
        message_id = message.message_id
        
        settings = get_channel_settings_by_id(channel_id)
        if not settings:
            logging.info(f"Сообщение из неотслеживаемого канала: ID={channel_id}, username={channel_username}")
            return
            
        config.VK_API_TOKEN = settings["access_token"]
        config.VK_GROUP_ID = settings["target_id"]
        
        if not refresh_token_if_needed():
            logging.error(f"Не удалось обновить токен для канала ID={channel_id}")
            return
            
        vk_session = VkApi(token=config.VK_API_TOKEN)
        config.vk = vk_session.get_api()
        
        try:
            # Находим соответствующий пост в ВК
            post_id = get_entry(message_id)
            
            # Получаем текст из сообщения
            if hasattr(message, 'text') and message.text:
                text = message.text
            elif hasattr(message, 'caption') and message.caption:
                text = message.caption
            else:
                logging.info(f"Редактируемое сообщение не содержит текста: ID={message_id}")
                return
                
            # Редактируем пост в ВК
            if edit_vk_post(post_id, text, message_id):
                logging.info(f"Успешно отредактирован пост {post_id} в ВК")
                log_to_db(
                    settings['user_id'], 
                    "info", 
                    f"Отредактировано сообщение из канала {channel_username or channel_id} в группе {settings.get('target_name') or config.VK_GROUP_ID}",
                    f"Сообщение: {message_id}, Пост: {post_id}"
                )
            else:
                logging.error(f"Не удалось отредактировать пост {post_id} в ВК")
                log_to_db(
                    settings['user_id'],
                    "error",
                    f"Ошибка при редактировании сообщения из канала {channel_username or channel_id}",
                    f"Сообщение: {message_id}, Пост: {post_id}"
                )
        except KeyError:
            logging.warning(f"Не найдено соответствие для сообщения {message_id}")
        except Exception as e:
            logging.error(f"Ошибка при обработке редактирования: {e}")
            log_to_db(
                settings['user_id'],
                "error",
                f"Ошибка при обработке редактирования сообщения из канала {channel_username or channel_id}",
                str(e)
            )
                
    except Exception as e:
        logging.error(f"Ошибка при обработке отредактированного сообщения: {e}")
