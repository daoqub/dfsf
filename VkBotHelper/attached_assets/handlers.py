import logging
import os
import random
import asyncio
from typing import Dict, List
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes
from vk_api import VkApi
from vk_api.upload import VkUpload
from PIL import Image

from vk_client import edit_vk_post, get_entry, add_entry, get_source_link_for_edit
from config import refresh_token_if_needed, format_owner_id
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

async def handle_media_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            photo = config.uploader.photo_wall(path)[0]
            attachments.append(f'photo{photo["owner_id"]}_{photo["id"]}')
            
        for path in video_list:
            video = config.uploader.video(path, name=os.path.basename(path))
            attachments.append(f'video{video["owner_id"]}_{video["video_id"]}')
            
        for path in doc_list:
            doc = config.uploader.document(path, title=os.path.basename(path))
            attachments.append(f'doc{doc["doc"]["owner_id"]}_{doc["doc"]["id"]}')
            
        for path in audio_list:
            audio = config.uploader.audio(path, title=os.path.basename(path))
            attachments.append(f'audio{audio["owner_id"]}_{audio["id"]}')
            
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
            
        # Удаляем временные файлы
        for path in photo_list + video_list + doc_list + audio_list:
            if os.path.exists(path):
                os.remove(path)
                
    except Exception as e:
        logging.error(f"Ошибка при обработке медиагруппы: {e}")

async def handle_photo_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает одиночные фото или видео"""
    try:
        message = update.channel_post
        if not message:
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
        config.uploader = VkUpload(config.vk)
        
        text = message.caption if message.caption else ''
        source_link = get_source_link(message)
        owner_id = format_owner_id(config.VK_GROUP_ID)
        
        if message.photo:
            random_number = random.randint(1000000, 9999999)
            path = f'./files/photo_{random_number}.jpg'
            
            if await download_file_with_retries(message.photo[-1].get_file(), path):
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
                    
                os.remove(path)
                
        elif message.video:
            if message.video.file_size > MAX_VIDEO_SIZE:
                post_text = f"{text}\n\nВидео доступно по ссылке: {source_link}"
                
                response = await asyncio.to_thread(
                    config.vk.wall.post,
                    owner_id=owner_id,
                    from_group=post_as_group,
                    message=post_text,
                    copyright=source_link
                )
                
                if response and 'post_id' in response:
                    add_entry(message.message_id, response['post_id'], settings['user_id'])
            else:
                random_number = random.randint(1000000, 9999999)
                path = f'./files/video_{random_number}.mp4'
                
                if await download_file_with_retries(message.video.get_file(), path):
                    video = config.uploader.video(path, name=message.video.file_name)
                    
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
                        
                    os.remove(path)
                    
    except Exception as e:
        logging.error(f"Ошибка при обработке фото или видео: {e}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает документы"""
    try:
        message = update.channel_post
        if not message:
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
        config.uploader = VkUpload(config.vk)
        
        text = message.caption if message.caption else ''
        source_link = get_source_link(message)
        owner_id = format_owner_id(config.VK_GROUP_ID)
        
        if message.document.file_size > MAX_VIDEO_SIZE:
            post_text = f"{text}\n\nДокумент доступен по ссылке: {source_link}"
            
            response = await asyncio.to_thread(
                config.vk.wall.post,
                owner_id=owner_id,
                from_group=post_as_group,
                message=post_text,
                copyright=source_link
            )
            
            if response and 'post_id' in response:
                add_entry(message.message_id, response['post_id'], settings['user_id'])
        else:
            random_number = random.randint(1000000, 9999999)
            path = f'./files/doc_{random_number}_{message.document.file_name}'
            
            if await download_file_with_retries(message.document.get_file(), path):
                doc = config.uploader.document(path, title=message.document.file_name)
                
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
                    
                os.remove(path)
                
    except Exception as e:
        logging.error(f"Ошибка при обработке документа: {e}")

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает аудиофайлы"""
    try:
        message = update.channel_post
        if not message:
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
        config.uploader = VkUpload(config.vk)
        
        text = message.caption if message.caption else ''
        source_link = get_source_link(message)
        owner_id = format_owner_id(config.VK_GROUP_ID)
        
        if message.audio.file_size > MAX_VIDEO_SIZE:
            post_text = f"{text}\n\nАудио доступно по ссылке: {source_link}"
            
            response = await asyncio.to_thread(
                config.vk.wall.post,
                owner_id=owner_id,
                from_group=post_as_group,
                message=post_text,
                copyright=source_link
            )
            
            if response and 'post_id' in response:
                add_entry(message.message_id, response['post_id'], settings['user_id'])
        else:
            random_number = random.randint(1000000, 9999999)
            path = f'./files/audio_{random_number}_{message.audio.file_name}'
            
            if await download_file_with_retries(message.audio.get_file(), path):
                audio = config.uploader.audio(path, title=message.audio.file_name)
                
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
                    
                os.remove(path)
                
    except Exception as e:
        logging.error(f"Ошибка при обработке аудио: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения"""
    try:
        message = update.channel_post
        if not message:
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
        config.uploader = VkUpload(config.vk)
        
        text = message.text
        source_link = get_source_link(message)
        owner_id = format_owner_id(config.VK_GROUP_ID)
        
        response = await asyncio.to_thread(
            config.vk.wall.post,
            owner_id=owner_id,
            from_group=post_as_group,
            message=text,
            copyright=source_link
        )
        
        if response and 'post_id' in response:
            add_entry(message.message_id, response['post_id'], settings['user_id'])
            
    except Exception as e:
        logging.error(f"Ошибка при обработке текстового сообщения: {e}")

async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает отредактированные сообщения"""
    try:
        message = update.edited_channel_post
        if not message:
            return
            
        channel_id = message.chat.id
        channel_username = message.chat.username
        
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
        
        # Получаем ID поста ВК
        post_id = get_entry(message.message_id)
        if not post_id:
            logging.warning(f"Не найден пост ВК для сообщения {message.message_id}")
            return
            
        text = message.text or message.caption or ''
        
        # Обновляем пост
        await asyncio.to_thread(edit_vk_post, post_id, text, message.message_id)
        
    except Exception as e:
        logging.error(f"Ошибка при обработке отредактированного сообщения: {e}") 