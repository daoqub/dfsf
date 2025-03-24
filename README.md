# Tg2Vk Bot

Бот для автоматического кросспостинга контента из Telegram-каналов в группы ВКонтакте.

## Функционал

- Автоматическое копирование постов из Telegram-каналов в группы ВК
- Поддержка различных типов контента:
  - Текстовые сообщения
  - Фотографии
  - Видео
  - Аудио
  - Видео заметки
  - Голосовые сообщения
  - Медиагруппы (альбомы, смешанные типы файлов)
- Сохранение ссылок на оригинальные посты
- Обработка редактирования сообщений
- Поддержка множества каналов и групп
- Система логирования и мониторинга

## Структура базы данных

### Основные таблицы:
- `telegram_channels` - информация о Telegram-каналах
- `vk_targets` - информация о группах ВК
- `crosspost_settings` - настройки кросспостинга
- `post_info` - информация о постах
- `posts` - основные записи постов
- `post_status` - статусы постов
- `post_metadata` - метаданные постов
- `post_content` - содержимое постов
- `post_media` - медиафайлы постов

Подробнее про таблицы и структуру данных:
 "table_name","columns"
"crosspost_settings","id, user_id, telegram_channel_id, vk_target_id, is_active, created_at, updated_at, post_as_group"
"logs","id, user_id, level, message, details, created_at"
"post_content","id, post_id, telegram_message_id, vk_post_id, content, created_at, updated_at"
"post_info","id, user_id, telegram_channel_id, vk_target_id, telegram_message_id, vk_post_id, content, status, error_message, processing_attempts, published_at, is_edited, edit_count, attachments_count, telegram_chat_id, channel_title, channel_username, vk_group_id, target_name, post_as_group, created_at, updated_at, is_active"
"post_media","id, post_id, media_group_id, file_id, file_type, file_size, width, height, duration, vk_attachment_id, created_at, processed"
"post_metadata","id, post_id, hashtags, mentions, links, attachments_count, is_edited, edit_count, created_at, updated_at"
"post_status","id, post_id, status, error_message, processing_attempts, published_at, created_at"
"posts","id, user_id, telegram_channel_id, vk_target_id, created_at, updated_at, is_active"
"referrals","id, referrer_id, referred_id, created_at"
"telegram_channels","id, user_id, channel_id, channel_title, channel_username, is_verified, created_at, last_post_id"
"users","id, telegram_id, username, first_name, last_name, referral_code, referrer_id, created_at, last_activity"
"vk_targets","id, user_id, target_id, target_name, target_type, access_token, refresh_token, expires_at, created_at, is_active"

## Требования

- Python 3.11+
- База данных Supabase
- Доступ к API Telegram и ВКонтакте

## Установка

1. Клонируйте репозиторий
2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate     # для Windows
```
3. Установите зависимости:
```bash
pip install -r requirements.txt
```
4. Создайте файл `.env` с необходимыми переменными:
```
TELEGRAM_API_TOKEN=ваш_токен_бота
SUPABASE_URL=ваш_url
SUPABASE_KEY=ваш_ключ
```

## Запуск

```bash
python main.py
```

## Логирование

Бот ведет подробное логирование в файл `bot.log` и выводит информацию в консоль. Логи содержат:
- Информацию о запуске и остановке бота
- Ошибки при обработке сообщений
- Статусы загрузки файлов
- Информацию о работе с базой данных
- Предупреждения и ошибки API

## Обработка ошибок

Бот имеет систему повторных попыток для:
- Загрузки файлов
- Отправки сообщений в ВК
- Обновления токенов
- Работы с базой данных

## Безопасность

- Все токены хранятся в базе данных
- Поддержка обновления токенов ВК
- Проверка прав доступа для каждого канала
- Безопасное хранение файлов 