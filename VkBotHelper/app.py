import os
import subprocess
from flask import Flask, render_template_string

app = Flask(__name__)

# Признак, запущен ли бот
bot_process = None

@app.route('/')
def index():
    bot_status = "Бот не запущен"
    
    # Проверяем, запущен ли бот
    global bot_process
    if bot_process is not None and bot_process.poll() is None:
        bot_status = "Бот запущен и работает"
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Telegram to VK Bot</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-header">
                            <h3 class="text-center">Telegram to VK Bot</h3>
                        </div>
                        <div class="card-body">
                            <div class="alert alert-info">
                                <h4>Статус бота:</h4>
                                <p>{{ bot_status }}</p>
                            </div>
                            <div class="d-grid gap-2">
                                <a href="/start_bot" class="btn btn-primary">Запустить бота</a>
                                <a href="/stop_bot" class="btn btn-danger">Остановить бота</a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, bot_status=bot_status)

@app.route('/start_bot')
def start_bot():
    global bot_process
    
    # Убедимся, что старый процесс не запущен
    if bot_process is not None and bot_process.poll() is None:
        return "Бот уже запущен"
    
    # Запускаем бот в фоновом режиме
    bot_process = subprocess.Popen(["python", "main.py"], 
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  text=True)
    
    return "Бот запущен. <a href='/'>Вернуться на главную</a>"

@app.route('/stop_bot')
def stop_bot():
    global bot_process
    
    if bot_process is not None and bot_process.poll() is None:
        bot_process.terminate()
        bot_process = None
        return "Бот остановлен. <a href='/'>Вернуться на главную</a>"
    
    return "Бот не запущен. <a href='/'>Вернуться на главную</a>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)