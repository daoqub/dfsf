import os
import logging
import asyncio
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from dotenv import load_dotenv

from config import init_supabase, log_to_db
from supabase_client import (
    get_channels, 
    get_vk_targets, 
    get_crosspost_settings,
    get_logs,
    add_channel,
    add_vk_target,
    add_crosspost_setting,
    get_post_history
)

# Загружаем переменные окружения
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "tg2vk_secret_key")

# Настройки для админки
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "password")

@app.route('/')
def index():
    """Главная страница"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Получаем статистику
    channels_count = len(get_channels())
    vk_targets_count = len(get_vk_targets())
    settings_count = len(get_crosspost_settings())
    posts = get_post_history(limit=5)
    logs = get_logs(limit=5)
    
    return render_template(
        'index.html', 
        channels_count=channels_count,
        vk_targets_count=vk_targets_count,
        settings_count=settings_count,
        posts=posts,
        logs=logs
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            flash('Вы успешно вошли в систему', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверные учетные данные', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Выход из системы"""
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app.route('/channels')
def channels():
    """Страница управления каналами"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    channels_list = get_channels()
    return render_template('channels.html', channels=channels_list)

@app.route('/channels/add', methods=['POST'])
def add_channel_route():
    """Добавление нового канала"""
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "Не авторизован"})
    
    try:
        data = request.json
        user_id = data.get('user_id', '1')  # По умолчанию ID 1, если не указан
        channel_id = data.get('channel_id')
        channel_title = data.get('channel_title', '')
        channel_username = data.get('channel_username', '')
        
        if not channel_id:
            return jsonify({"success": False, "error": "ID канала обязателен"})
        
        # Преобразуем channel_id в целое число, если это возможно
        try:
            channel_id = int(channel_id)
        except ValueError:
            return jsonify({"success": False, "error": "ID канала должен быть числом"})
        
        channel_db_id = add_channel(user_id, channel_id, channel_title, channel_username)
        
        if channel_db_id:
            log_to_db(user_id, "info", f"Добавлен новый канал: {channel_title or channel_username or channel_id}")
            return jsonify({"success": True, "id": channel_db_id})
        else:
            return jsonify({"success": False, "error": "Не удалось добавить канал"})
    
    except Exception as e:
        logging.error(f"Ошибка при добавлении канала: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/vk_targets')
def vk_targets():
    """Страница управления целями VK"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    vk_targets_list = get_vk_targets()
    return render_template('vk_targets.html', vk_targets=vk_targets_list)

@app.route('/vk_targets/add', methods=['POST'])
def add_vk_target_route():
    """Добавление новой цели VK"""
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "Не авторизован"})
    
    try:
        data = request.json
        user_id = data.get('user_id', '1')  # По умолчанию ID 1, если не указан
        target_id = data.get('target_id')
        target_name = data.get('target_name', '')
        access_token = data.get('access_token')
        refresh_token = data.get('refresh_token', None)
        
        if not target_id or not access_token:
            return jsonify({"success": False, "error": "ID группы и токен доступа обязательны"})
        
        # Преобразуем target_id в целое число, если это возможно
        try:
            target_id = int(target_id)
        except ValueError:
            return jsonify({"success": False, "error": "ID группы должен быть числом"})
        
        # Устанавливаем срок действия токена на 3 месяца, если не указан иной
        expires_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        target_db_id = add_vk_target(user_id, target_id, target_name, access_token, refresh_token, expires_at)
        
        if target_db_id:
            log_to_db(user_id, "info", f"Добавлена новая цель VK: {target_name or target_id}")
            return jsonify({"success": True, "id": target_db_id})
        else:
            return jsonify({"success": False, "error": "Не удалось добавить цель VK"})
    
    except Exception as e:
        logging.error(f"Ошибка при добавлении цели VK: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/crosspost_settings')
def crosspost_settings():
    """Страница управления настройками кросспостинга"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    settings_list = get_crosspost_settings()
    channels_list = get_channels()
    vk_targets_list = get_vk_targets()
    
    return render_template(
        'crosspost_settings.html', 
        settings=settings_list,
        channels=channels_list,
        vk_targets=vk_targets_list
    )

@app.route('/crosspost_settings/add', methods=['POST'])
def add_crosspost_setting_route():
    """Добавление новой настройки кросспостинга"""
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "Не авторизован"})
    
    try:
        data = request.json
        user_id = data.get('user_id', '1')  # По умолчанию ID 1, если не указан
        telegram_channel_id = data.get('telegram_channel_id')
        vk_target_id = data.get('vk_target_id')
        post_as_group = data.get('post_as_group', 1)
        
        if not telegram_channel_id or not vk_target_id:
            return jsonify({"success": False, "error": "ID канала и ID группы обязательны"})
        
        setting_db_id = add_crosspost_setting(user_id, telegram_channel_id, vk_target_id, post_as_group)
        
        if setting_db_id:
            log_to_db(user_id, "info", f"Добавлена новая настройка кросспостинга: Канал {telegram_channel_id} -> Группа {vk_target_id}")
            return jsonify({"success": True, "id": setting_db_id})
        else:
            return jsonify({"success": False, "error": "Не удалось добавить настройку кросспостинга"})
    
    except Exception as e:
        logging.error(f"Ошибка при добавлении настройки кросспостинга: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/logs')
def logs():
    """Страница просмотра логов"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    logs_list = get_logs()
    return render_template('logs.html', logs=logs_list)

@app.route('/api/logs')
def api_logs():
    """API для получения логов"""
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "Не авторизован"})
    
    limit = request.args.get('limit', 100, type=int)
    logs_list = get_logs(limit=limit)
    return jsonify({"success": True, "logs": logs_list})

@app.route('/api/posts')
def api_posts():
    """API для получения истории постов"""
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "Не авторизован"})
    
    limit = request.args.get('limit', 100, type=int)
    posts_list = get_post_history(limit=limit)
    return jsonify({"success": True, "posts": posts_list})

@app.route('/api/status')
def api_status():
    """API для проверки статуса бота"""
    if not session.get('logged_in'):
        return jsonify({"success": False, "error": "Не авторизован"})
    
    # Проверяем соединение с Supabase
    supabase_connected = init_supabase()
    
    return jsonify({
        "success": True, 
        "status": "online" if supabase_connected else "partial",
        "supabase_connected": supabase_connected,
        "telegram_api_configured": bool(os.getenv('TELEGRAM_API_TOKEN')),
        "uptime": "Unknown"  # В будущем можно добавить отслеживание времени работы
    })

async def run_webapp():
    """Запускает веб-приложение в отдельном потоке"""
    logging.info("Запуск веб-интерфейса Tg2Vk Bot")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
