import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import requests
from bs4 import BeautifulSoup

API_TOKEN = '7773785455:AAGvA88X-acyRRzN0QimGQAieSKrX7nDpTk'
ADMIN_IDS = [7699241002, 1110784441]  # ID админов бота
NOTIFY_CHAT_ID = -4664465936  # ID группы для уведомлений

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


# Инициализация базы данных
async def init_db():
    async with aiosqlite.connect('streamers.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS streamers (
                username TEXT PRIMARY KEY,
                phone TEXT,
                description TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                username TEXT,
                chat_id INTEGER,
                message_id INTEGER,
                PRIMARY KEY (username, chat_id, message_id)
            )
        ''')
        # New table for chat admins
        await db.execute('''
            CREATE TABLE IF NOT EXISTS chat_admins (
                chat_id INTEGER,
                admin_id INTEGER,
                PRIMARY KEY (chat_id, admin_id)
            )
        ''')
        await db.commit()


# Проверка стрима
def get_tiktok_live(username):
    url = f"https://www.tiktok.com/@{username}/live"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except:
        return False

    soup = BeautifulSoup(response.text, "html.parser")
    return bool(soup.find("script", id="VideoObject"))


# Класс состояний для добавления стримера
class AddStreamer(StatesGroup):
    waiting_for_data = State()


# Команда старт
@dp.message_handler(commands=['start'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def cmd_start(message: types.Message):
    help_text = """TTLiveDAR - Tik Tok Live Detection and Ranging

Команды для всех:
- Нажатие кнопки ""
/list - показать список стримеров (с [+] активные, [-] неактивные)
/view [username] - Посмотреть информацию об стримере

Команды для администраторов:
/add - добавить нового стримера 
   • Формат: username, телефон, описание
/rem [username] - удалить стримера
/offon [username] - включить/выключить проверку стримера
/alloffon - включить/выключить проверку всех стримеров

Управление правами:
/admin [user_id] - добавить администратора бота 
/admin_rem [user_id] - удалить администратора бота
/admin_list - список администраторов бота

Примеры:
- /add 
   Bobovka
   79991234567
   Бобовка бешасть агрессивная
- /rem Bobovka
- /offon Bobovka
- /view Bobovka
- /admin 123456789
"""
    await message.answer(help_text)


# Admin command handlers йоу
@dp.message_handler(commands=['admin'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def add_admin(message: types.Message):
    # Only group admins can add new admins
    chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if chat_member.status not in ['creator', 'administrator']:
        return await message.answer("Только администраторы группы могут добавлять новых администраторов бота.")

    # Get the chat_id to add as admin
    admin_id = message.get_args()
    if not admin_id:
        return await message.answer("Укажите ID пользователя: /admin {user_id}")

    try:
        admin_id = int(admin_id)
        async with aiosqlite.connect('streamers.db') as db:
            await db.execute('INSERT OR IGNORE INTO chat_admins (chat_id, admin_id) VALUES (?, ?)',
                             (message.chat.id, admin_id))
            await db.commit()
        await message.answer(f"Пользователь {admin_id} добавлен как администратор бота в этом чате.")
    except ValueError:
        await message.answer("Неверный формат ID пользователя.")
    except Exception as e:
        await message.answer(f"Ошибка при добавлении администратора: {str(e)}")


@dp.message_handler(commands=['admin_rem'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def remove_admin(message: types.Message):
    # Only group admins can remove admins
    chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if chat_member.status not in ['creator', 'administrator']:
        return await message.answer("Только администраторы группы могут удалять администраторов бота.")

    # Get the chat_id to remove from admins
    admin_id = message.get_args()
    if not admin_id:
        return await message.answer("Укажите ID пользователя: /admin_rem {user_id}")

    try:
        admin_id = int(admin_id)
        async with aiosqlite.connect('streamers.db') as db:
            await db.execute('DELETE FROM chat_admins WHERE chat_id = ? AND admin_id = ?',
                             (message.chat.id, admin_id))
            rows_affected = await db.total_changes()
            await db.commit()

        if rows_affected > 0:
            await message.answer(f"Пользователь {admin_id} удален из администраторов бота в этом чате.")
        else:
            await message.answer(f"Пользователь {admin_id} не является администратором бота в этом чате.")
    except ValueError:
        await message.answer("Неверный формат ID пользователя.")
    except Exception as e:
        await message.answer(f"Ошибка при удалении администратора: {str(e)}")


@dp.message_handler(commands=['admin_list'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def list_admins(message: types.Message):
    async with aiosqlite.connect('streamers.db') as db:
        cursor = await db.execute('SELECT admin_id FROM chat_admins WHERE chat_id = ?', (message.chat.id,))
        admins = await cursor.fetchall()

    if not admins:
        return await message.answer("В этом чате нет дополнительных администраторов бота.")

    admin_list = [str(admin[0]) for admin in admins]
    text = "Администраторы бота в этом чате:\n" + "\n".join(admin_list)
    await message.answer(text)


# Изменение существующих обработчиков команд для проверки разрешений администратора чата
def check_chat_admin(func):
    async def wrapper(message: types.Message):
        # Check if the user is a group administrator or in the chat admins list
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status in ['creator', 'administrator']:
            return await func(message)

        async with aiosqlite.connect('streamers.db') as db:
            cursor = await db.execute('SELECT 1 FROM chat_admins WHERE chat_id = ? AND admin_id = ?',
                                      (message.chat.id, message.from_user.id))
            is_bot_admin = await cursor.fetchone()

        if is_bot_admin:
            return await func(message)

        await message.answer("У вас недостаточно прав для выполнения этой команды.")

    return wrapper


@dp.message_handler(commands=['view'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def cmd_view(message: types.Message):
    username = message.get_args()
    if not username:
        return await message.answer("Укажите username: /view username")

    async with aiosqlite.connect('streamers.db') as db:
        cursor = await db.execute(
            'SELECT username, phone, description, is_active FROM streamers WHERE username = ?',
            (username,)
        )
        streamer = await cursor.fetchone()

    if not streamer:
        return await message.answer(f"Стример {username} не найден в базе")

    username, phone, desc, is_active = streamer
    status = "🟢 Активен" if is_active == 1 else "🔴 Неактивен"

    profile_text = (
        f"📋 Профиль стримера\n\n"
        f"👤 Username: {username}\n"
        f"📱 Телефон: {phone}\n"
        f"📝 Описание: {desc}\n"
        f"⚡️ Статус: {status}\n\n"
        f"🔗 Ссылки:\n"
        f"▫️ TikTok: https://www.tiktok.com/@{username}\n"
        f"▫️ WhatsApp: wa.me/{phone}\n"
        f"▫️ Telegram: t.me/{phone}\n"
        f"▫️ Viber: viber.click/{phone}"
    )

    await message.answer(profile_text)


# Команда добавления стримера
@dp.message_handler(commands=['add'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
@check_chat_admin
async def cmd_add(message: types.Message):
    # Existing add command implementation remains the same
    await AddStreamer.waiting_for_data.set()
    await message.answer("Отправьте данные в формате (Одним сообщением):\n"
                         "Username в тик токе\n"
                         "Номер телефона\n"
                         "Описание для уведомления")


# Обработчик данных для добавления
@dp.message_handler(state=AddStreamer.waiting_for_data, chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def process_add(message: types.Message, state: FSMContext):
    try:
        data = message.text.split('\n')
        username = data[0].strip()
        phone = data[1].strip()
        desc = data[2].strip()

        async with aiosqlite.connect('streamers.db') as db:
            await db.execute('INSERT INTO streamers (username, phone, description) VALUES (?, ?, ?)',
                             (username, phone, desc))
            await db.commit()

        await message.answer("Стример успешно добавлен!")
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")
    finally:
        await state.finish()


# Команда удаления стримера
@dp.message_handler(commands=['rem'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
@check_chat_admin
async def cmd_rem(message: types.Message):
    # Existing remove command implementation remains the same
    username = message.get_args()
    if not username:
        return await message.answer("Укажите username: /rem username")

    async with aiosqlite.connect('streamers.db') as db:
        await db.execute('DELETE FROM streamers WHERE username = ?', (username,))
        await db.execute('DELETE FROM notifications WHERE username = ?', (username,))
        await db.commit()

    await message.answer(f"Стример {username} удален")


@dp.message_handler(commands=['offon'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
@check_chat_admin
async def toggle_streamer_monitoring(message: types.Message):
    username = message.get_args()
    if not username:
        return await message.answer("Укажите username: /offon {username}")

    async with aiosqlite.connect('streamers.db') as db:
        cursor = await db.execute('SELECT is_active FROM streamers WHERE username = ?', (username,))
        result = await cursor.fetchone()

        if not result:
            return await message.answer(f"Стример {username} не найден в базе")

        new_status = 1 if result[0] == 0 else 0
        await db.execute('UPDATE streamers SET is_active = ? WHERE username = ?', (new_status, username))
        await db.commit()

    status_text = "включена" if new_status == 1 else "отключена"
    await message.answer(f"Проверка стримера {username} {status_text}")


@dp.message_handler(commands=['alloffon'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
@check_chat_admin
async def toggle_all_streamers_monitoring(message: types.Message):
    async with aiosqlite.connect('streamers.db') as db:
        cursor = await db.execute('SELECT is_active FROM streamers LIMIT 1')
        result = await cursor.fetchone()

        if not result:
            return await message.answer("Список стримеров пуст")

        current_status = result[0]
        new_status = 1 if current_status == 0 else 0
        await db.execute('UPDATE streamers SET is_active = ?', (new_status,))
        await db.commit()

    status_text = "включена" if new_status == 1 else "отключена"
    await message.answer(f"Проверка всех стримеров {status_text}")


# Команда списка стримеров
@dp.message_handler(commands=['list'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def cmd_list(message: types.Message):
    async with aiosqlite.connect('streamers.db') as db:
        cursor = await db.execute('SELECT username, is_active FROM streamers')
        streamers = await cursor.fetchall()

    if not streamers:
        return await message.answer("Список стримеров пуст")

    text = "Отслеживаемые стримеры:\n" + "\n".join([
        f"[+] {s[0]}" if s[1] == 1 else f"[-] {s[0]}" for s in streamers
    ])
    await message.answer(text)


# Обработчик кнопки "Уничтожено"
@dp.callback_query_handler(lambda c: c.data.startswith('viewed_'))
async def mark_viewed(callback: types.CallbackQuery):
    username = "_".join(callback.data.split("_")[1:])

    async with aiosqlite.connect('streamers.db') as db:
        await db.execute('UPDATE streamers SET is_active = 1 WHERE username = ?', (username,))
        cursor = await db.execute('SELECT chat_id, message_id FROM notifications WHERE username = ?', (username,))
        notifications = await cursor.fetchall()
        await db.execute('DELETE FROM notifications WHERE username = ?', (username,))
        await db.commit()

    for chat_id, message_id in notifications:
        try:
            new_markup = types.InlineKeyboardMarkup()
            new_markup.add(types.InlineKeyboardButton(
                "✅ Эфир завершён ✅",
                callback_data="already_pressed"
            ))
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=new_markup
            )
        except Exception as e:
            print(f"Ошибка при редактировании сообщения {message_id}: {e}")

    await callback.answer("Стример помечен как неактивный!")


# Обработчик уже нажатой кнопки
@dp.callback_query_handler(lambda c: c.data == 'already_pressed')
async def handle_already_pressed(callback: types.CallbackQuery):
    await callback.answer("Этот стример уже завершил трансляцию!", show_alert=True)


async def auto_mark_viewed(username, chat_id, message_id):
    await asyncio.sleep(1200)  # 20 минут = 1200 секунд

    async with aiosqlite.connect('streamers.db') as db:
        cursor = await db.execute('SELECT * FROM notifications WHERE username = ? AND chat_id = ? AND message_id = ?',
                                  (username, chat_id, message_id))
        notification = await cursor.fetchone()

        if notification:
            # Удаляем запись из таблицы notifications
            await db.execute('DELETE FROM notifications WHERE username = ? AND chat_id = ? AND message_id = ?',
                             (username, chat_id, message_id))

            # Обновляем значение is_active в таблице streamers
            await db.execute('UPDATE streamers SET is_active = 1 WHERE username = ?', (username,))

            await db.commit()

            new_markup = types.InlineKeyboardMarkup()
            new_markup.add(types.InlineKeyboardButton(
                "Эфир завершён 💯",
                callback_data="already_pressed"
            ))
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=new_markup
            )


async def check_streams():
    while True:
        async with aiosqlite.connect('streamers.db') as db:
            cursor = await db.execute('SELECT * FROM streamers WHERE is_active = 1')
            streamers = await cursor.fetchall()

        tasks = []
        for streamer in streamers:
            username, phone, desc, is_active = streamer
            tasks.append(check_single_streamer(username, phone, desc))

        await asyncio.gather(*tasks)
        await asyncio.sleep(10)


async def check_single_streamer(username, phone, desc):
    if get_tiktok_live(username):
        message_text = (
            f"⚠️ TTLiveDAR Обнаружил трансляцию! ⚠️\n\n"
            f"{desc}\n\n"
            f"🧑‍💻: {username}\n"
            f"🔗: https://www.tiktok.com/@{username}/live\n\n"
            f"📞: {phone}\n\n"
            f" 🟩 : wa.me/{phone}\n"
            f" 🟦 : t.me/{phone}\n"
            f" 🟪 : viber.click/{phone}"
        )

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "☑️ Эфир Уничтожен ☑️",
            callback_data=f"viewed_{username}"
        ))

        try:
            msg = await bot.send_message(NOTIFY_CHAT_ID, message_text, reply_markup=markup)
            async with aiosqlite.connect('streamers.db') as db:
                await db.execute(
                    'INSERT INTO notifications (username, chat_id, message_id) VALUES (?, ?, ?)',
                    (username, NOTIFY_CHAT_ID, msg.message_id)
                )
                await db.commit()

            # Запускаем таймер для автоматического завершения отслеживания через 20 минут
            asyncio.create_task(auto_mark_viewed(username, NOTIFY_CHAT_ID, msg.message_id))

        except Exception as e:
            print(f"Ошибка при отправке сообщения: {e}")

        async with aiosqlite.connect('streamers.db') as db:
            await db.execute('UPDATE streamers SET is_active = 0 WHERE username = ?', (username,))
            await db.commit()


async def main():
    await init_db()
    asyncio.create_task(check_streams())
    await dp.start_polling()


if __name__ == '__main__':
    asyncio.run(main())