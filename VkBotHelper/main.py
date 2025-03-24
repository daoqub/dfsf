import logging
import os
import subprocess
import threading
import time
import json
from pathlib import Path
from datetime import datetime
import re
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv(override=True)

# Проверяем наличие переменных окружения
logging.basicConfig(level=logging.INFO)
logging.info(f"SUPABASE_URL: {os.getenv('SUPABASE_URL')}")
logging.info(f"SUPABASE_KEY: {'*' * len(os.getenv('SUPABASE_KEY')) if os.getenv('SUPABASE_KEY') else 'None'}")
logging.info(f"TELEGRAM_API_TOKEN: {'*' * 10 if os.getenv('TELEGRAM_API_TOKEN') else 'None'}")

# Исходный файл main.py
MAIN_ORIG = "main.py.orig"
# Новое имя для исходного файла, если он уже был переименован
MAIN_BOT = "main_bot.py"

def setup_logging():
    """Настраивает логирование"""
    Path("logs").mkdir(exist_ok=True)
    log_file = f"logs/webapp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

def run_bot():
    """Запускает Telegram бота в отдельном процессе"""
    global bot_process
    
    try:
        # Определяем, какой скрипт запускать
        bot_script = MAIN_BOT if os.path.exists(MAIN_BOT) else MAIN_ORIG
        
        if not os.path.exists(bot_script):
            logging.error(f"Файл бота {bot_script} не найден!")
            return
        
        logging.info(f"Запускаем бота из файла: {bot_script}")
        
        # Запуск бота в отдельном процессе
        env = os.environ.copy()  # Копируем текущие переменные окружения
        bot_process = subprocess.Popen(
            ['python', bot_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env
        )
        
        logging.info(f"Бот запущен с PID: {bot_process.pid}")
        
        # Логирование вывода бота
        for line in bot_process.stdout:
            logging.info(f"BOT: {line.strip()}")
            
        return_code = bot_process.wait()
        if return_code != 0:
            logging.error(f"Бот завершился с кодом {return_code}")
        else:
            logging.info("Бот завершил работу нормально")
        
        # Сбрасываем процесс бота
        bot_process = None
            
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}")
        bot_process = None

# Инициализируем Supabase клиент для модуля
import json
from supabase import create_client, Client

# Глобальная переменная для Supabase клиента
sb_client = None

def init_supabase():
    """Инициализирует клиент Supabase"""
    global sb_client
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if supabase_url and supabase_key:
        try:
            sb_client = create_client(supabase_url, supabase_key)
            logging.info("Модуль main.py: Supabase успешно инициализирован")
            return True
        except Exception as e:
            logging.error(f"Модуль main.py: Ошибка при инициализации Supabase: {e}")
    else:
        logging.error(f"Модуль main.py: Не указаны параметры подключения к Supabase URL={supabase_url}")
    
    return False

# Получение данных из базы и логов
def get_logs(limit=100):
    """Получает логи из базы данных или файла"""
    global sb_client
    logs = []
    
    # Пробуем инициализировать Supabase если не инициализирован
    if sb_client is None:
        init_supabase()
    
    # Пробуем получить логи из Supabase
    if sb_client is not None:
        try:
            response = sb_client.table("logs").select("*").order("created_at", desc=True).limit(limit).execute()
            if response.data:
                logs = response.data
                logging.info(f"Получено {len(logs)} записей логов из Supabase")
        except Exception as e:
            logging.warning(f"Ошибка при получении логов из базы данных: {e}")
    
    # Если логов из базы нет, читаем из файла
    if not logs:
        try:
            if os.path.exists("bot.log"):
                with open("bot.log", "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    
                    for line in lines[-limit:]:
                        parts = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\w+) - (\w+) - (.*)", line)
                        if parts:
                            timestamp, name, level, message = parts.groups()
                            logs.append({
                                "timestamp": timestamp,
                                "level": level,
                                "message": message,
                                "details": ""
                            })
                logging.info(f"Получено {len(logs)} записей логов из файла bot.log")
        except Exception as e:
            logging.error(f"Ошибка при чтении файла лога: {e}")
    
    return logs

def get_posts(limit=50):
    """Получает историю постов"""
    global sb_client
    posts = []
    
    # Пробуем инициализировать Supabase если не инициализирован
    if sb_client is None:
        init_supabase()
        
    # Пробуем получить историю постов из Supabase
    if sb_client is not None:
        try:
            response = sb_client.table("post_info").select("*").order("created_at", desc=True).limit(limit).execute()
            if response.data:
                posts = response.data
                logging.info(f"Получено {len(posts)} записей истории постов из Supabase")
        except Exception as e:
            logging.warning(f"Ошибка при получении истории постов: {e}")
    
    return posts

# Flask приложение
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

# Глобальная переменная для процесса бота
bot_process = None

# Функция для мониторинга процесса бота
def monitor_bot_process(process):
    """Мониторит процесс бота и обновляет глобальную переменную"""
    global bot_process
    try:
        if process is None:
            return
        
        return_code = process.wait()
        if return_code != 0:
            logging.error(f"Бот завершился с кодом {return_code}")
        else:
            logging.info("Бот завершил работу нормально")
        
        # Очищаем глобальную переменную только если это тот же процесс
        if bot_process is process:
            bot_process = None
    except Exception as e:
        logging.error(f"Ошибка при мониторинге процесса бота: {e}")

# Функция для чтения вывода процесса
def read_process_output(process):
    """Читает и логирует вывод процесса"""
    try:
        if process and process.stdout:
            for line in process.stdout:
                if line:
                    logging.info(f"BOT: {line.strip()}")
    except Exception as e:
        logging.error(f"Ошибка при чтении вывода процесса: {e}")

# Функция для инициализации бота
def initialize_bot():
    """Инициализирует и запускает бота"""
    global bot_process
    
    # Если бот уже запущен и работает, просто возвращаемся
    if bot_process is not None and bot_process.poll() is None:
        logging.info(f"Бот уже запущен с PID: {bot_process.pid}")
        return True
    
    try:
        # Определяем путь к скрипту бота
        bot_script = MAIN_BOT if os.path.exists(MAIN_BOT) else MAIN_ORIG
        
        if not os.path.exists(bot_script):
            logging.error(f"Файл бота {bot_script} не найден!")
            return False
        
        logging.info(f"Запускаем бота из файла: {bot_script}")
        
        # Запускаем бота в отдельном процессе
        env = os.environ.copy()  # Копируем текущие переменные окружения
        process = subprocess.Popen(
            ['python', bot_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env
        )
        
        # Устанавливаем глобальную переменную
        bot_process = process
        
        logging.info(f"Бот запущен с PID: {bot_process.pid}")
        
        # Запускаем отдельный поток для чтения вывода бота
        output_thread = threading.Thread(target=read_process_output, args=(process,))
        output_thread.daemon = True
        output_thread.start()
        
        # Запускаем отдельный поток для мониторинга статуса процесса
        monitor_thread = threading.Thread(target=monitor_bot_process, args=(process,))
        monitor_thread.daemon = True
        monitor_thread.start()
        
        return True
        
    except Exception as e:
        logging.error(f"Ошибка при инициализации бота: {e}")
        return False

# Создаем ручной маршрут для запуска бота
@app.route('/start_bot', methods=['GET'])
def start_bot_route():
    """API для запуска бота вручную"""
    try:
        initialize_bot()
        return jsonify({"status": "success", "message": "Бот успешно запущен"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Ошибка при запуске бота: {e}"})

# Переменная для отслеживания попыток инициализации
bot_init_attempted = False

@app.route('/')
def index():
    """Главная страница"""
    # Пытаемся автоматически запустить бота при первом запросе
    global bot_init_attempted
    if not bot_init_attempted:
        try:
            initialize_bot()
            bot_init_attempted = True
            logging.info("Автоматическая попытка запуска бота при первом запросе")
        except Exception as e:
            logging.error(f"Ошибка при автоматическом запуске бота: {e}")
            bot_init_attempted = True
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Telegram to VK Bot</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
        <style>
            .log-info { color: var(--bs-info); }
            .log-warning { color: var(--bs-warning); }
            .log-error { color: var(--bs-danger); }
            .log-date { font-size: 0.85em; color: var(--bs-secondary); }
        </style>
    </head>
    <body>
        <div class="container mt-4">
            <div class="row">
                <div class="col-12">
                    <div class="card mb-4">
                        <div class="card-header bg-primary text-white">
                            <h3 class="text-center m-0">Telegram to VK Bot</h3>
                        </div>
                        <div class="card-body">
                            <div class="alert alert-info">
                                <h4>Статус:</h4>
                                <p id="bot-status">Ожидание проверки статуса бота...</p>
                            </div>
                            <div class="d-grid gap-2">
                                <button id="start-bot-btn" class="btn btn-success mb-2">Запустить бота</button>
                                <button id="check-status-btn" class="btn btn-info mb-2">Проверить статус</button>
                                <button id="refresh-data-btn" class="btn btn-secondary">Обновить данные</button>
                            </div>
                            <p class="mt-3 mb-3">
                                Бот кросспостинга из Telegram в VK автоматически мониторит сообщения
                                в настроенных Telegram-каналах и публикует их в заданные группы ВКонтакте.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="row">
                <!-- Настройки кросспостинга -->
                <div class="col-12 mb-4">
                    <div class="card">
                        <div class="card-header bg-primary text-white">
                            <h4 class="m-0">Настройки кросспостинга</h4>
                        </div>
                        <div class="card-body">
                            <div class="alert alert-info">
                                <i class="bi bi-info-circle-fill me-2"></i>
                                Бот настроен на мониторинг каналов Telegram и публикацию их содержимого в группы ВКонтакте согласно настройкам из Supabase.
                            </div>
                            <div id="crosspost-settings-info">
                                <div class="text-center py-3">
                                    <div class="spinner-border text-primary" role="status">
                                        <span class="visually-hidden">Загрузка...</span>
                                    </div>
                                    <p class="mt-2">Загрузка настроек...</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- История постов -->
                <div class="col-md-6">
                    <div class="card mb-4">
                        <div class="card-header bg-success text-white">
                            <h4 class="m-0">История постов</h4>
                        </div>
                        <div class="card-body p-0">
                            <div class="table-responsive">
                                <table class="table table-striped table-hover mb-0">
                                    <thead>
                                        <tr>
                                            <th>Время</th>
                                            <th>Сообщение Telegram</th>
                                            <th>Пост VK</th>
                                            <th>Детали</th>
                                        </tr>
                                    </thead>
                                    <tbody id="posts-table-body">
                                        <tr>
                                            <td colspan="4" class="text-center">Загрузка данных...</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Логи -->
                <div class="col-md-6">
                    <div class="card mb-4">
                        <div class="card-header bg-info text-white">
                            <h4 class="m-0">Логи</h4>
                        </div>
                        <div class="card-body p-0">
                            <div class="table-responsive">
                                <table class="table table-striped table-hover mb-0">
                                    <thead>
                                        <tr>
                                            <th>Время</th>
                                            <th>Уровень</th>
                                            <th>Сообщение</th>
                                        </tr>
                                    </thead>
                                    <tbody id="logs-table-body">
                                        <tr>
                                            <td colspan="3" class="text-center">Загрузка данных...</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            // Форматирование даты
            function formatDate(dateString) {
                const date = new Date(dateString);
                return date.toLocaleString('ru-RU');
            }
            
            // Загрузка логов
            function loadLogs() {
                fetch('/api/logs')
                    .then(response => response.json())
                    .then(logs => {
                        updateLogsTable(logs);
                        // Обновляем логи каждые 10 секунд
                        setTimeout(loadLogs, 10000);
                    })
                    .catch(error => {
                        console.error('Ошибка загрузки логов:', error);
                        setTimeout(loadLogs, 10000);
                    });
            }
            
            // Обновление таблицы логов
            function updateLogsTable(logs) {
                const tableBody = document.getElementById('logs-table-body');
                if (logs.length === 0) {
                    tableBody.innerHTML = '<tr><td colspan="3" class="text-center">Нет данных</td></tr>';
                    return;
                }
                
                tableBody.innerHTML = '';
                logs.forEach(log => {
                    const row = document.createElement('tr');
                    
                    const timeCell = document.createElement('td');
                    timeCell.className = 'log-date';
                    timeCell.textContent = log.timestamp || formatDate(log.created_at);
                    
                    const levelCell = document.createElement('td');
                    levelCell.className = 'log-' + (log.level || 'info').toLowerCase();
                    levelCell.textContent = log.level || 'INFO';
                    
                    const messageCell = document.createElement('td');
                    messageCell.textContent = log.message;
                    
                    row.appendChild(timeCell);
                    row.appendChild(levelCell);
                    row.appendChild(messageCell);
                    tableBody.appendChild(row);
                });
            }
            
            // Загрузка настроек кросспостинга
            function loadSettings() {
                const settingsContainer = document.getElementById('crosspost-settings-info');
                
                fetch('/api/settings')
                    .then(response => response.json())
                    .then(settings => {
                        updateSettingsInfo(settings);
                    })
                    .catch(error => {
                        console.error('Ошибка загрузки настроек:', error);
                        settingsContainer.innerHTML = `
                            <div class="alert alert-danger">
                                <i class="bi bi-exclamation-triangle-fill me-2"></i>
                                Ошибка при загрузке настроек кросспостинга
                            </div>
                        `;
                    });
            }
            
            // Обновление информации о настройках
            function updateSettingsInfo(settings) {
                const settingsContainer = document.getElementById('crosspost-settings-info');
                
                // Если нет данных или все массивы пустые
                if (!settings || 
                    (settings.channels.length === 0 && 
                     settings.vk_targets.length === 0 && 
                     settings.crosspost_settings.length === 0)) {
                    
                    settingsContainer.innerHTML = `
                        <div class="alert alert-warning">
                            <i class="bi bi-exclamation-circle-fill me-2"></i>
                            Настройки кросспостинга не найдены. Используйте Supabase для настройки каналов и целей.
                        </div>
                    `;
                    return;
                }
                
                let html = '';
                
                // Создаем карточки с информацией о настройках
                if (settings.channels.length > 0) {
                    html += `
                        <div class="card mb-3">
                            <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                                <h5 class="m-0">Каналы Telegram (${settings.channels.length})</h5>
                                <span class="badge bg-light text-primary">${settings.channels.length > 10 ? 'Показаны первые 10 из ' + settings.channels.length : settings.channels.length}</span>
                            </div>
                            <div class="card-body p-0">
                                <div class="table-responsive">
                                    <table class="table table-striped table-hover mb-0">
                                        <thead>
                                            <tr>
                                                <th>ID канала</th>
                                                <th>Название</th>
                                                <th>Username</th>
                                                <th>Статус</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                    `;
                    
                    // Показываем только первые 10 каналов, если их много
                    const channelsToShow = settings.channels.length > 10 ? 
                        settings.channels.slice(0, 10) : settings.channels;
                    
                    channelsToShow.forEach(channel => {
                        // Проверяем, есть ли активные настройки кросспостинга для данного канала
                        const hasActiveSettings = settings.crosspost_settings.some(
                            setting => setting.telegram_channel_id === channel.id && setting.is_active
                        );
                        
                        html += `
                            <tr>
                                <td>${channel.channel_id}</td>
                                <td>${channel.channel_title || 'Нет названия'}</td>
                                <td>${channel.channel_username ? '@' + channel.channel_username : 'Приватный канал'}</td>
                                <td>
                                    <span class="badge ${hasActiveSettings ? 'bg-success' : 'bg-warning'}">
                                        ${hasActiveSettings ? 'Активен' : 'Ожидает настройки'}
                                    </span>
                                </td>
                            </tr>
                        `;
                    });
                    
                    html += `
                                        </tbody>
                                    </table>
                                </div>
                                ${settings.channels.length > 10 ? 
                                    `<div class="p-2 text-center">
                                        <button class="btn btn-sm btn-outline-primary" onclick="alert('Полный список доступен в Supabase')">
                                            Показать все ${settings.channels.length} каналов
                                        </button>
                                    </div>` : ''}
                            </div>
                        </div>
                    `;
                }
                
                if (settings.vk_targets.length > 0) {
                    html += `
                        <div class="card mb-3">
                            <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                                <h5 class="m-0">Цели ВКонтакте (${settings.vk_targets.length})</h5>
                                <span class="badge bg-light text-primary">${settings.vk_targets.length > 10 ? 'Показаны первые 10 из ' + settings.vk_targets.length : settings.vk_targets.length}</span>
                            </div>
                            <div class="card-body p-0">
                                <div class="table-responsive">
                                    <table class="table table-striped table-hover mb-0">
                                        <thead>
                                            <tr>
                                                <th>ID цели</th>
                                                <th>Название</th>
                                                <th>Токен</th>
                                                <th>Статус</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                    `;
                    
                    // Показываем только первые 10 целей, если их много
                    const targetsToShow = settings.vk_targets.length > 10 ? 
                        settings.vk_targets.slice(0, 10) : settings.vk_targets;
                    
                    targetsToShow.forEach(target => {
                        // Проверяем, есть ли активные настройки кросспостинга для данной цели
                        const hasActiveSettings = settings.crosspost_settings.some(
                            setting => setting.vk_target_id === target.id && setting.is_active
                        );
                        
                        // Проверяем срок действия токена
                        const hasValidToken = target.access_token && 
                            (!target.expires_at || new Date(target.expires_at) > new Date());
                        
                        html += `
                            <tr>
                                <td>${target.target_id}</td>
                                <td>${target.target_name || 'Нет названия'}</td>
                                <td>${target.access_token ? 
                                    `<span class="badge bg-${hasValidToken ? 'success' : 'warning'} text-light">
                                        ●●●●●●●●●● ${hasValidToken ? '' : '(истекает)'}
                                    </span>` : 
                                    '<span class="badge bg-danger text-light">Нет токена</span>'}</td>
                                <td>
                                    <span class="badge ${hasActiveSettings ? 'bg-success' : 'bg-warning'}">
                                        ${hasActiveSettings ? 'Активен' : 'Ожидает настройки'}
                                    </span>
                                </td>
                            </tr>
                        `;
                    });
                    
                    html += `
                                        </tbody>
                                    </table>
                                </div>
                                ${settings.vk_targets.length > 10 ? 
                                    `<div class="p-2 text-center">
                                        <button class="btn btn-sm btn-outline-primary" onclick="alert('Полный список доступен в Supabase')">
                                            Показать все ${settings.vk_targets.length} целей
                                        </button>
                                    </div>` : ''}
                            </div>
                        </div>
                    `;
                }
                
                if (settings.crosspost_settings.length > 0) {
                    html += `
                        <div class="card mb-3">
                            <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                                <h5 class="m-0">Настройки кросспостинга (${settings.crosspost_settings.length})</h5>
                                <span class="badge bg-light text-primary">${settings.crosspost_settings.length > 10 ? 'Показаны первые 10 из ' + settings.crosspost_settings.length : settings.crosspost_settings.length}</span>
                            </div>
                            <div class="card-body p-0">
                                <div class="table-responsive">
                                    <table class="table table-striped table-hover mb-0">
                                        <thead>
                                            <tr>
                                                <th>Telegram канал</th>
                                                <th>VK цель</th>
                                                <th>Настройки</th>
                                                <th>Статус</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                    `;
                    
                    // Показываем только первые 10 настроек, если их много
                    const settingsToShow = settings.crosspost_settings.length > 10 ? 
                        settings.crosspost_settings.slice(0, 10) : settings.crosspost_settings;
                    
                    settingsToShow.forEach(setting => {
                        // Найдем название канала и цели
                        const channel = settings.channels.find(c => c.channel_id === setting.telegram_channel_id);
                        const target = settings.vk_targets.find(t => t.target_id === setting.vk_target_id);
                        
                        // Проверяем, активны ли канал и цель
                        const isActive = setting.is_active !== false; // По умолчанию активно, если не указано иное
                        const hasValidChannel = Boolean(channel);
                        const hasValidTarget = Boolean(target) && target.access_token;
                        const isFullyValid = isActive && hasValidChannel && hasValidTarget;
                        
                        html += `
                            <tr>
                                <td>${channel ? 
                                    `<span class="text-${hasValidChannel ? 'success' : 'danger'}">${channel.channel_title || channel.channel_id}</span>` : 
                                    `<span class="text-danger">${setting.telegram_channel_id} (не найден)</span>`}</td>
                                <td>${target ? 
                                    `<span class="text-${hasValidTarget ? 'success' : 'warning'}">${target.target_name || target.target_id}</span>` : 
                                    `<span class="text-danger">${setting.vk_target_id} (не найден)</span>`}</td>
                                <td>${setting.post_as_group ? 'От имени группы' : 'От имени пользователя'}</td>
                                <td>
                                    <span class="badge ${isFullyValid ? 'bg-success' : 'bg-danger'}">
                                        ${isFullyValid ? 'Активен' : 'Проблема настройки'}
                                    </span>
                                </td>
                            </tr>
                        `;
                    });
                    
                    html += `
                                        </tbody>
                                    </table>
                                </div>
                                ${settings.crosspost_settings.length > 10 ? 
                                    `<div class="p-2 text-center">
                                        <button class="btn btn-sm btn-outline-primary" onclick="alert('Полный список доступен в Supabase')">
                                            Показать все ${settings.crosspost_settings.length} настроек
                                        </button>
                                    </div>` : ''}
                            </div>
                        </div>
                    `;
                }
                
                settingsContainer.innerHTML = html;
            }
            
            // Загрузка истории постов
            function loadPosts() {
                fetch('/api/posts')
                    .then(response => response.json())
                    .then(posts => {
                        updatePostsTable(posts);
                        // Обновляем историю постов каждые 10 секунд
                        setTimeout(loadPosts, 10000);
                    })
                    .catch(error => {
                        console.error('Ошибка загрузки истории постов:', error);
                        setTimeout(loadPosts, 10000);
                    });
            }
            
            // Обновление таблицы истории постов
            function updatePostsTable(posts) {
                const tableBody = document.getElementById('posts-table-body');
                if (posts.length === 0) {
                    tableBody.innerHTML = '<tr><td colspan="4" class="text-center">Нет данных</td></tr>';
                    return;
                }
                
                tableBody.innerHTML = '';
                posts.forEach(post => {
                    const row = document.createElement('tr');
                    
                    const timeCell = document.createElement('td');
                    timeCell.className = 'log-date';
                    timeCell.textContent = formatDate(post.created_at);
                    
                    const messageCell = document.createElement('td');
                    if (post.telegram_message_id) {
                        messageCell.innerHTML = `<span class="badge bg-info">
                            ID: ${post.telegram_message_id}
                        </span>`;
                    } else {
                        messageCell.innerHTML = '<span class="badge bg-warning">Нет данных</span>';
                    }
                    
                    const postIdCell = document.createElement('td');
                    if (post.vk_post_id) {
                        postIdCell.innerHTML = `<span class="badge bg-success">
                            ID: ${post.vk_post_id}
                        </span>`;
                    } else {
                        postIdCell.innerHTML = '<span class="badge bg-danger">Ошибка публикации</span>';
                    }
                    
                    const detailsCell = document.createElement('td');
                    let userText = post.user_id ? `Пользователь: ${post.user_id}` : '';
                    let channelText = post.channel_id ? `<br>Канал: ${post.channel_id}` : '';
                    let targetText = post.target_id ? `<br>Цель: ${post.target_id}` : '';
                    
                    detailsCell.innerHTML = `
                        <button class="btn btn-sm btn-outline-primary" 
                            data-bs-toggle="tooltip" 
                            title="${userText}${channelText}${targetText}">
                            Детали
                        </button>
                    `;
                    
                    row.appendChild(timeCell);
                    row.appendChild(messageCell);
                    row.appendChild(postIdCell);
                    row.appendChild(detailsCell);
                    tableBody.appendChild(row);
                });
            }
            
            // Функция для запуска бота
            function startBot() {
                const statusEl = document.getElementById('bot-status');
                const startBtn = document.getElementById('start-bot-btn');
                
                statusEl.textContent = 'Запуск бота...';
                startBtn.disabled = true;
                
                fetch('/start_bot')
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            statusEl.textContent = 'Бот успешно запущен';
                            statusEl.className = 'text-success';
                        } else {
                            statusEl.textContent = 'Ошибка запуска: ' + data.message;
                            statusEl.className = 'text-danger';
                            startBtn.disabled = false;
                        }
                        // Обновляем логи после запуска
                        loadLogs();
                    })
                    .catch(error => {
                        console.error('Ошибка при запуске бота:', error);
                        statusEl.textContent = 'Ошибка сервера при запуске бота';
                        statusEl.className = 'text-danger';
                        startBtn.disabled = false;
                    });
            }
            
            // Функция для проверки статуса бота
            function checkBotStatus() {
                const statusEl = document.getElementById('bot-status');
                const startBtn = document.getElementById('start-bot-btn');
                
                statusEl.textContent = 'Проверка статуса...';
                
                fetch('/api/status')
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'running') {
                            statusEl.textContent = 'Бот запущен и работает (PID: ' + data.pid + ')';
                            statusEl.className = 'text-success';
                            startBtn.disabled = true;
                        } else if (data.status === 'crashed') {
                            statusEl.textContent = 'Бот аварийно завершил работу';
                            statusEl.className = 'text-danger';
                            startBtn.disabled = false;
                        } else {
                            statusEl.textContent = 'Бот не запущен';
                            statusEl.className = 'text-warning';
                            startBtn.disabled = false;
                        }
                        
                        // Обновляем логи
                        loadLogs();
                    })
                    .catch(error => {
                        console.error('Ошибка при проверке статуса бота:', error);
                        statusEl.textContent = 'Ошибка проверки статуса';
                        statusEl.className = 'text-danger';
                    });
            }
            
            // Функция для обновления всех данных
            function refreshAllData() {
                // Показываем индикатор загрузки для каждой секции
                document.getElementById('logs-table-body').innerHTML = '<tr><td colspan="3" class="text-center"><div class="spinner-border spinner-border-sm" role="status"></div> Обновление...</td></tr>';
                document.getElementById('posts-table-body').innerHTML = '<tr><td colspan="4" class="text-center"><div class="spinner-border spinner-border-sm" role="status"></div> Обновление...</td></tr>';
                document.getElementById('crosspost-settings-info').innerHTML = '<div class="text-center py-3"><div class="spinner-border text-primary" role="status"></div><p class="mt-2">Обновление настроек...</p></div>';
                
                // Обновляем статус и все данные
                checkBotStatus();
                loadLogs();
                loadPosts();
                loadSettings();
                
                // Показываем сообщение об успешном обновлении
                const statusContainer = document.getElementById('bot-status');
                const oldText = statusContainer.textContent;
                const oldClass = statusContainer.className;
                
                statusContainer.textContent += " (Данные обновлены)";
                
                setTimeout(() => {
                    statusContainer.textContent = oldText;
                    statusContainer.className = oldClass;
                }, 3000);
            }
            
            // Загружаем данные при загрузке страницы
            document.addEventListener('DOMContentLoaded', function() {
                // Проверяем статус бота сразу при загрузке страницы
                checkBotStatus();
                
                // Загружаем логи, историю постов и настройки
                loadLogs();
                loadPosts();
                loadSettings();
                
                // Добавляем обработчики событий для кнопок
                document.getElementById('start-bot-btn').addEventListener('click', startBot);
                document.getElementById('check-status-btn').addEventListener('click', checkBotStatus);
                document.getElementById('refresh-data-btn').addEventListener('click', refreshAllData);
                
                // Устанавливаем автоматическую проверку статуса каждые 30 секунд
                setInterval(checkBotStatus, 30000);
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/api/logs')
def api_logs():
    """API для получения логов"""
    logs = get_logs(100)
    return jsonify(logs)

@app.route('/api/posts')
def api_posts():
    """API для получения истории постов"""
    posts = get_posts(50)
    return jsonify(posts)

@app.route('/api/settings')
def api_settings():
    """API для получения настроек кросспостинга"""
    global sb_client
    
    settings = {
        "channels": [],
        "vk_targets": [],
        "crosspost_settings": []
    }
    
    # Пробуем инициализировать Supabase если не инициализирован
    if sb_client is None:
        init_supabase()
    
    if sb_client is not None:
        try:
            # Получаем список каналов
            response = sb_client.table("telegram_channels").select("*").execute()
            if response.data:
                settings["channels"] = response.data
                
            # Получаем список целей VK
            response = sb_client.table("vk_targets").select("*").execute()
            if response.data:
                settings["vk_targets"] = response.data
                
            # Получаем настройки кросспостинга
            response = sb_client.table("crosspost_settings").select("*").execute()
            if response.data:
                settings["crosspost_settings"] = response.data
                
        except Exception as e:
            logging.warning(f"Ошибка при получении настроек кросспостинга: {e}")
    
    return jsonify(settings)

@app.route('/api/status')
def api_status():
    """API для проверки статуса бота"""
    global bot_process
    
    if bot_process is None:
        status = "stopped"
        pid = None
    elif bot_process.poll() is None:
        status = "running"
        pid = bot_process.pid
    else:
        status = "crashed"
        pid = bot_process.pid
        
    # Получаем последние логи для информации о состоянии
    logs = get_logs(5)
    
    return jsonify({
        "status": status,
        "pid": pid,
        "last_logs": logs
    })

if __name__ == "__main__":
    # Проверяем, не был ли уже переименован файл
    if not os.path.exists(MAIN_BOT) and os.path.exists(__file__) and not os.path.exists(MAIN_ORIG):
        # Переименовываем текущий файл в temporary
        os.rename(__file__, "main.py.temp")
        # Переименовываем оригинальный main.py
        os.rename("main.py", MAIN_BOT)
        # Переименовываем временный файл обратно в main.py
        os.rename("main.py.temp", "main.py")
        logging.info(f"Файл main.py переименован в {MAIN_BOT}")
    
    setup_logging()
    logging.info("Запуск веб-приложения и бота")
    
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запускаем Flask приложение
    from waitress import serve
    serve(app, host="0.0.0.0", port=5000)