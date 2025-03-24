/**
 * Tg2Vk Bot - Основной JavaScript файл
 */

// Функция для форматирования дат
function formatDate(dateString) {
    if (!dateString) return '';
    
    const date = new Date(dateString);
    return date.toLocaleString();
}

// Функция для обновления статуса бота
function checkBotStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            const statusIndicator = document.getElementById('statusIndicator');
            const botStatus = document.getElementById('botStatus');
            
            if (!statusIndicator || !botStatus) return;
            
            if (data.success) {
                statusIndicator.className = 'status-indicator status-' + data.status;
                botStatus.textContent = 'Статус: ' + (data.status === 'online' ? 'Онлайн' : 
                                       data.status === 'partial' ? 'Частично работает' : 'Офлайн');
            } else {
                statusIndicator.className = 'status-indicator status-offline';
                botStatus.textContent = 'Статус: Недоступен';
            }
        })
        .catch(error => {
            console.error('Ошибка при проверке статуса:', error);
            const statusIndicator = document.getElementById('statusIndicator');
            const botStatus = document.getElementById('botStatus');
            
            if (statusIndicator && botStatus) {
                statusIndicator.className = 'status-indicator status-offline';
                botStatus.textContent = 'Статус: Ошибка соединения';
            }
        });
}

// Функция для загрузки логов
function loadLogs(limit = 100) {
    fetch(`/api/logs?limit=${limit}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateLogsTable(data.logs);
            } else {
                console.error('Ошибка при загрузке логов:', data.error);
            }
        })
        .catch(error => {
            console.error('Ошибка при загрузке логов:', error);
        });
}

// Функция для обновления таблицы логов
function updateLogsTable(logs) {
    const allLogsBody = document.getElementById('allLogsBody');
    const infoLogsBody = document.getElementById('infoLogsBody');
    const warningLogsBody = document.getElementById('warningLogsBody');
    const errorLogsBody = document.getElementById('errorLogsBody');
    
    if (!allLogsBody) return;
    
    // Очищаем таблицы
    allLogsBody.innerHTML = '';
    if (infoLogsBody) infoLogsBody.innerHTML = '';
    if (warningLogsBody) warningLogsBody.innerHTML = '';
    if (errorLogsBody) errorLogsBody.innerHTML = '';
    
    // Заполняем таблицы данными
    if (logs && logs.length > 0) {
        logs.forEach(log => {
            // Создаем строку для всех логов
            const allRow = createLogRow(log);
            allLogsBody.appendChild(allRow);
            
            // Распределяем по соответствующим таблицам
            if (log.level === 'info' && infoLogsBody) {
                const infoRow = createLogRow(log, false);
                infoLogsBody.appendChild(infoRow);
            } else if (log.level === 'warning' && warningLogsBody) {
                const warningRow = createLogRow(log, false);
                warningLogsBody.appendChild(warningRow);
            } else if (log.level === 'error' && errorLogsBody) {
                const errorRow = createLogRow(log, false);
                errorLogsBody.appendChild(errorRow);
            }
        });
    } else {
        // Если логов нет, выводим сообщение
        allLogsBody.innerHTML = '<tr><td colspan="6" class="text-center">Нет данных</td></tr>';
        if (infoLogsBody) infoLogsBody.innerHTML = '<tr><td colspan="5" class="text-center">Нет информационных логов</td></tr>';
        if (warningLogsBody) warningLogsBody.innerHTML = '<tr><td colspan="5" class="text-center">Нет предупреждений</td></tr>';
        if (errorLogsBody) errorLogsBody.innerHTML = '<tr><td colspan="5" class="text-center">Нет ошибок</td></tr>';
    }
}

// Функция для создания строки таблицы логов
function createLogRow(log, includeLevel = true) {
    const row = document.createElement('tr');
    
    // ID
    const idCell = document.createElement('td');
    idCell.textContent = log.id;
    row.appendChild(idCell);
    
    // Уровень (если нужен)
    if (includeLevel) {
        const levelCell = document.createElement('td');
        let badge = document.createElement('span');
        badge.className = 'badge';
        
        if (log.level === 'info') {
            badge.classList.add('bg-info');
            badge.textContent = 'INFO';
        } else if (log.level === 'error') {
            badge.classList.add('bg-danger');
            badge.textContent = 'ERROR';
        } else if (log.level === 'warning') {
            badge.classList.add('bg-warning');
            badge.textContent = 'WARNING';
        } else {
            badge.classList.add('bg-secondary');
            badge.textContent = log.level;
        }
        
        levelCell.appendChild(badge);
        row.appendChild(levelCell);
    }
    
    // Сообщение
    const messageCell = document.createElement('td');
    messageCell.textContent = log.message;
    row.appendChild(messageCell);
    
    // Пользователь
    const userCell = document.createElement('td');
    userCell.textContent = log.user_id;
    row.appendChild(userCell);
    
    // Дата
    const dateCell = document.createElement('td');
    dateCell.textContent = formatDate(log.created_at);
    row.appendChild(dateCell);
    
    // Действия
    const actionsCell = document.createElement('td');
    const viewButton = document.createElement('button');
    viewButton.className = 'btn btn-sm btn-outline-info';
    viewButton.innerHTML = '<i data-feather="eye"></i>';
    viewButton.onclick = function() { viewLog(log.id); };
    actionsCell.appendChild(viewButton);
    row.appendChild(actionsCell);
    
    return row;
}

// Функция для загрузки истории постов
function loadPosts(limit = 100) {
    fetch(`/api/posts?limit=${limit}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updatePostsTable(data.posts);
            } else {
                console.error('Ошибка при загрузке истории постов:', data.error);
            }
        })
        .catch(error => {
            console.error('Ошибка при загрузке истории постов:', error);
        });
}

// Функция для обновления таблицы истории постов
function updatePostsTable(posts) {
    const postsHistoryBody = document.getElementById('postsHistoryBody');
    
    if (!postsHistoryBody) return;
    
    // Очищаем таблицу
    postsHistoryBody.innerHTML = '';
    
    // Заполняем таблицу данными
    if (posts && posts.length > 0) {
        posts.forEach(post => {
            const row = document.createElement('tr');
            
            // ID
            const idCell = document.createElement('td');
            idCell.textContent = post.id;
            row.appendChild(idCell);
            
            // Канал
            const channelCell = document.createElement('td');
            channelCell.textContent = post.channel_username || post.telegram_channel_id;
            row.appendChild(channelCell);
            
            // Группа VK
            const groupCell = document.createElement('td');
            groupCell.textContent = post.target_name || post.vk_target_id;
            row.appendChild(groupCell);
            
            // ID сообщения TG
            const tgMsgCell = document.createElement('td');
            tgMsgCell.textContent = post.telegram_message_id;
            row.appendChild(tgMsgCell);
            
            // ID поста VK
            const vkPostCell = document.createElement('td');
            vkPostCell.textContent = post.vk_post_id;
            row.appendChild(vkPostCell);
            
            // Статус
            const statusCell = document.createElement('td');
            let badge = document.createElement('span');
            badge.className = 'badge';
            
            if (post.status === 'published') {
                badge.classList.add('bg-success');
                badge.textContent = 'Опубликован';
            } else if (post.status === 'error') {
                badge.classList.add('bg-danger');
                badge.textContent = 'Ошибка';
            } else if (post.status === 'edited') {
                badge.classList.add('bg-info');
                badge.textContent = 'Изменен';
            } else {
                badge.classList.add('bg-secondary');
                badge.textContent = post.status;
            }
            
            statusCell.appendChild(badge);
            row.appendChild(statusCell);
            
            // Дата
            const dateCell = document.createElement('td');
            dateCell.textContent = formatDate(post.created_at);
            row.appendChild(dateCell);
            
            // Действия
            const actionsCell = document.createElement('td');
            const viewButton = document.createElement('button');
            viewButton.className = 'btn btn-sm btn-outline-info';
            viewButton.innerHTML = '<i data-feather="eye"></i>';
            viewButton.onclick = function() { viewPost(post.id); };
            actionsCell.appendChild(viewButton);
            row.appendChild(actionsCell);
            
            postsHistoryBody.appendChild(row);
        });
    } else {
        // Если постов нет, выводим сообщение
        postsHistoryBody.innerHTML = '<tr><td colspan="8" class="text-center">Нет истории публикаций</td></tr>';
    }
    
    // Обновляем иконки Feather
    if (typeof feather !== 'undefined') {
        feather.replace();
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Первоначальная проверка статуса бота
    checkBotStatus();
    
    // Запускаем интервал проверки статуса каждые 30 секунд
    setInterval(checkBotStatus, 30000);
    
    // Инициализация иконок Feather
    if (typeof feather !== 'undefined') {
        feather.replace();
    }
});
