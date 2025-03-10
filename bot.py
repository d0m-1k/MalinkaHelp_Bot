import telebot
import sqlite3
import time
import yaml
from telebot import types

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

with open("lang.yaml", "r") as f:
    lang = yaml.safe_load(f)

bot = telebot.TeleBot(config["BOT_TOKEN"])
ADMINS = config["ADMINS"]

conn = sqlite3.connect('app.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS logs
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER,
                   action TEXT,
                   timestamp TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS users
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER,
                   username TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS admins
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER)''')

for admin_id in ADMINS:
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (admin_id,))
conn.commit()

user_job_start_time = {}
user_log_page = {}

@bot.message_handler(commands=['помощь'])
def send_help(message):
    bot.reply_to(message, lang["help_text"])

@bot.message_handler(commands=['спам'])
def job_command(message):
    user_id = message.from_user.id
    username = message.from_user.username
    command = message.text.split()[1]

    if command == 'начать':
        if user_id in user_job_start_time:
            bot.reply_to(message, lang["job_already_started"])
        else:
            user_job_start_time[user_id] = time.time()
            log_action(user_id, f"пользователь: @{username} начал работу")
            bot.reply_to(message, lang["job_started"])

    elif command == 'конец':
        if user_id not in user_job_start_time:
            bot.reply_to(message, lang["job_not_started"])
        else:
            start_time = user_job_start_time.pop(user_id)
            end_time = time.time()
            duration = end_time - start_time
            minutes, seconds = divmod(duration, 60)
            log_action(user_id, f"пользователь: @{username} окончил работу (проработал {int(minutes)} минут {int(seconds)} секунд)")
            bot.reply_to(message, lang["job_stopped"].format(minutes=int(minutes), seconds=int(seconds)))

@bot.message_handler(commands=['принять'])
def accept_player(message):
    user_id = message.from_user.id
    username = message.from_user.username
    try:
        player_nickname = message.text.split()[1]
        log_action(user_id, f"пользователь: @{username} принял игрока: {player_nickname}")
        bot.reply_to(message, lang["player_accepted"].format(nickname=player_nickname))
    except IndexError:
        bot.reply_to(message, lang["player_nickname_missing"])

@bot.message_handler(commands=['получить'])
def send_logs_file(message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        bot.reply_to(message, lang["no_permission"])
        return

    command = message.text.split()[1]
    if command == 'логи':
        with open('logs.txt', 'rb') as log_file:
            bot.send_document(message.chat.id, log_file)

@bot.message_handler(commands=['логи'])
def send_logs(message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        bot.reply_to(message, lang["no_permission"])
        return

    if user_id not in user_log_page:
        user_log_page[user_id] = 0

    logs = get_logs(user_log_page[user_id])
    if not logs:
        bot.reply_to(message, lang["logs_empty"])
        return

    log_text = "\n".join(logs)
    bot.reply_to(message, log_text)

    markup = types.InlineKeyboardMarkup()
    if user_log_page[user_id] > 0:
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="prev_page"))
    if len(logs) == 10:
        markup.add(types.InlineKeyboardButton("➡️ Вперед", callback_data="next_page"))
    bot.send_message(message.chat.id, lang["logs_page"].format(page=user_log_page[user_id] + 1), reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_pagination(call):
    user_id = call.from_user.id
    if user_id not in ADMINS:
        return

    if call.data == "prev_page":
        user_log_page[user_id] -= 1
    elif call.data == "next_page":
        user_log_page[user_id] += 1

    bot.delete_message(call.message.chat.id, call.message.message_id)
    send_logs(call.message)

@bot.message_handler(commands=['добавить'])
def add_user(message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        bot.reply_to(message, lang["no_permission"])
        return

    try:
        username = message.text.split()[2]
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            bot.reply_to(message, lang["user_already_added"].format(username=username))
        else:
            cursor.execute("INSERT INTO users (username) VALUES (?)", (username,))
            conn.commit()
            bot.reply_to(message, lang["user_added"].format(username=username))
    except IndexError:
        bot.reply_to(message, "Укажите username.")

@bot.message_handler(commands=['удалить'])
def remove_user(message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        bot.reply_to(message, lang["no_permission"])
        return

    try:
        username = message.text.split()[2]
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            cursor.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()
            bot.reply_to(message, lang["user_removed"].format(username=username))
        else:
            bot.reply_to(message, lang["user_not_found"].format(username=username))
    except IndexError:
        bot.reply_to(message, "Укажите username.")

def log_action(user_id, action):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] - {action}\n"
    with open('logs.txt', 'a') as log_file:
        log_file.write(log_message)
    cursor.execute("INSERT INTO logs (user_id, action, timestamp) VALUES (?, ?, ?)", (user_id, action, timestamp))
    conn.commit()

def get_logs(page=0, limit=10):
    cursor.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, page * limit))
    logs = cursor.fetchall()
    log_texts = []
    for log in logs:
        log_texts.append(f"[{log[3]}] - {log[2]}")
    return log_texts

if __name__ == "__main__":
    print(f"Bot login as @{bot.user.username}")
    bot.polling(none_stop=True)
