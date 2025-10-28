import asyncio
import logging
import asyncpg
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile
from aiogram.filters import Command, CommandObject
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TOKEN, DB_URL
from db.db import create_appeal, add_message, init_db, get_notification_recipients, get_message_template, init_message_templates, get_current_time_in_timezone, format_time_for_display

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


class RoomInput(StatesGroup):
    waiting_room = State()


class UserAppeal(StatesGroup):
    waiting_text = State()
    waiting_reply = State()
    waiting_custom_problem = State()
    waiting_comment = State()


async def show_main_menu(message: Message):
    await send_welcome_with_photo(message)
    room_prompt = await get_message_template('room_prompt')
    await message.answer(room_prompt or "Введите номер вашей комнаты:")


async def show_service_menu(message: Message, state: FSMContext):
    service_iron_text = await get_message_template('service_iron') or "🧹 Нужен утюг и гладильная доска"
    service_laundry_text = await get_message_template('service_laundry') or "👕 Услуги прачечной"
    service_other_text = await get_message_template('service_other') or "❓ Другой вопрос"
    contacts_text = await get_message_template('menu_contacts') or "📞 Контакты"
    back_main_menu_text = await get_message_template('back_main_menu') or "🏠 Назад в главное меню"
    service_menu_title = await get_message_template('service_menu_title') or "Выберите услугу:"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=service_iron_text, callback_data="service_iron")],
        [InlineKeyboardButton(text=service_laundry_text, callback_data="service_laundry")],
        [InlineKeyboardButton(text="🔧 Техническая проблема в номере", callback_data="service_technical")],
        [InlineKeyboardButton(text="🍽 Услуги ресторана", callback_data="service_restaurant")],
        [InlineKeyboardButton(text=service_other_text, callback_data="service_other")],
        [InlineKeyboardButton(text=contacts_text, callback_data="menu_contacts"), InlineKeyboardButton(text=back_main_menu_text, callback_data="back_main_menu")]
    ])
    await message.answer(service_menu_title, reply_markup=keyboard)


@router.message(Command("start"))
async def start(message: Message, command: CommandObject, state: FSMContext):
    args = command.args
    if args and args.isdigit():
        await state.update_data(room=args)
        await send_welcome_with_photo(message)
        await show_service_menu(message, state)
        return

    await show_main_menu(message)
    await state.set_state(RoomInput.waiting_room)

async def send_welcome_with_photo(message: Message):
    welcome_text = await get_message_template('welcome_text')
    if not welcome_text:
        welcome_text = """
🏨 Добро пожаловать в отель "Спасская"!

Мы рады приветствовать вас в нашем боте. Здесь вы можете:

🛎 Заказать услуги номера
🍽 Ознакомиться с меню ресторана
🔧 Сообщить о технических проблемах
📞 Связаться с нашими службами

Для начала работы укажите номер вашей комнаты.
"""

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        photo_path = os.path.join(current_dir, '..', 'images', 'hotel_welcome.jpg')
        photo_path = os.path.abspath(photo_path)

        logger.info(f"Looking for photo at: {photo_path}")
        logger.info(f"Photo exists: {os.path.exists(photo_path)}")

        if os.path.exists(photo_path):
            photo = FSInputFile(photo_path)
            await message.answer_photo(photo, caption=welcome_text)
            logger.info("Photo sent successfully")
        else:
            logger.warning(f"Photo not found at {photo_path}")
            await message.answer(welcome_text)
    except Exception as e:
        logger.error(f"Error sending photo: {e}")
        logger.error(f"Exception type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await message.answer(welcome_text)


@router.callback_query(F.data == "back_main_menu")
async def back_main_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await show_main_menu(callback.message)
    await state.set_state(RoomInput.waiting_room)


@router.callback_query(F.data == "menu_contacts")
async def menu_contacts(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    contacts_text = await get_message_template('contacts_text')
    if not contacts_text:
        contacts_text = """
📞 Контакты отеля:
+7 (345) 255-00-08
8 800 700-55-08

📞 Ресепшн: вн. 101
🍽 Ресторан: вн. 122

🌐 Сайт: hotel-spasskaya.ru
📧 Почта: info@hotel-spasskaya.ru
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к услугам", callback_data="back_services")]
    ])
    await callback.message.answer(contacts_text, reply_markup=keyboard)


@router.message(RoomInput.waiting_room)
async def get_room(message: Message, state: FSMContext):
    invalid_room_msg = await get_message_template('invalid_room')
    room_confirmed_msg = await get_message_template('room_confirmed')

    if not message.text or not message.text.isdigit():
        await message.answer(invalid_room_msg or "❌ Номер комнаты должен быть. Попробуйте ещё раз или отправьте /cancel.")
        return
    await state.update_data(room=message.text)
    await message.answer((room_confirmed_msg or "✅ Номер комнаты: {room}").format(room=message.text))
    await show_service_menu(message, state)


@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    await state.clear()
    cancel_message = await get_message_template('cancel_message')
    await message.answer(cancel_message or "Операция отменена. Если нужно — начните заново /start.")


@router.message(Command("help"))
async def help_cmd(message: Message):
    help_text = await get_message_template('help_text')
    if not help_text:
        help_text = """🏨 <b>Бот отеля 'Спасская'</b>

📋 <b>Команды:</b>
/start — главное меню
/help — получить справку
/cancel — отменить текущее действие

📩 <b>Как сделать обращение:</b>
1. Нажмите /start или выберите "Обращение (ресепшен)"
2. Укажите номер вашей комнаты
3. Опишите вашу проблему или пожелание

💬 <b>Ответы на сообщения:</b>
• Когда администратор ответит, вы сможете ответить обратно
• Нажмите кнопку "Ответить" под сообщением
• Напишите ваш ответ и отправьте

🔄 <b>Если проблема не решена:</b>
Нажмите "Не решено" под сообщением о выполнении

📞 <b>Быстрый старт:</b>
Можно сразу указать комнату: /start 101"""

    await message.answer(help_text, parse_mode="HTML")


async def send_user_message_notification(appeal_id, username, room, message):
    try:
        recipients = await get_notification_recipients(active_only=True)

        current_time = get_current_time_in_timezone()
        time_str = format_time_for_display(current_time)

        notification_template = await get_message_template('user_message_notification')
        if notification_template:
            notification_text = notification_template.format(
                username=username or 'пользователь',
                room=room,
                message=message[:100] + ('...' if len(message) > 100 else ''),
                appeal_id=appeal_id,
                time=time_str
            )
        else:
            notification_text = f"""💬 <b>Новое сообщение от пользователя</b>

👤 Пользователь: @{username or 'пользователь'} (комната {room})
📝 Сообщение: {message[:100]}{'...' if len(message) > 100 else ''}

🔔 Обращение #{appeal_id}

🕗 Время: {time_str}"""

        for recipient in recipients:
            try:
                await bot.send_message(
                    chat_id=recipient['chat_id'],
                    text=notification_text,
                    parse_mode="HTML",
                    disable_notification=False
                )
                logger.info(f"User message notification sent to {recipient['chat_id']} for appeal #{appeal_id}")
            except Exception as e:
                logger.error(f"Failed to send user message notification to {recipient['chat_id']}: {e}")
    except Exception as e:
        logger.error(f"Error in send_user_message_notification: {e}")


async def send_new_appeal_notification(appeal_id, room, service_type, description, comment=None):
    try:
        recipients = await get_notification_recipients(active_only=True)

        service_type_names = {
            'iron': await get_message_template('service_iron') or '🧺 Утюг и гладильная доска',
            'laundry': await get_message_template('service_laundry') or '👕 Услуги прачечной',
            'technical_ac': await get_message_template('tech_ac') or '❄️ Кондиционер',
            'technical_wifi': await get_message_template('tech_wifi') or '📶 WiFi',
            'technical_tv': await get_message_template('tech_tv') or '📺 Телевизор',
            'technical_other': await get_message_template('tech_other') or '🔧 Другие технические проблемы',
            'restaurant_call': await get_message_template('connect_restaurant') or '📞 Соединить с рестораном',
            'custom': '❓ Другие вопросы',
            'other': '❓ Прочее'
        }

        service_name = service_type_names.get(service_type, service_type)

        current_time = get_current_time_in_timezone()
        time_str = format_time_for_display(current_time)

        notification_template = await get_message_template('new_appeal_notification')
        if notification_template:
            notification_text = notification_template.format(
                appeal_id=appeal_id,
                room=room,
                service_name=service_name,
                description=description,
                time=time_str
            )
        else:
            notification_text = f"""🔔 <b>Новая заявка #{appeal_id}</b>

🛏️ Комната: <b>{room}</b>
📋 Тип: {service_name}
✉️ Описание: {description}
"""

        if comment:
            notification_text += f"💬 Комментарий: {comment}\n"

        notification_text += f"\n🕗 Время: {time_str}"

        for recipient in recipients:
            try:
                await bot.send_message(
                    chat_id=recipient['chat_id'],
                    text=notification_text,
                    parse_mode="HTML",
                    disable_notification=False
                )
                logger.info(f"Notification sent to {recipient['chat_id']} for appeal #{appeal_id}")
            except Exception as e:
                logger.error(f"Failed to send notification to {recipient['chat_id']}: {e}")
    except Exception as e:
        logger.error(f"Error in send_new_appeal_notification: {e}")


async def create_service_request(user_id, username, room, service_type, description, optional_comment=None):
    conn = await asyncpg.connect(DB_URL)
    try:
        appeal_id = await conn.fetchval(
            "INSERT INTO appeals (user_id, username, room, text, request_type, optional_comment) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            user_id, username, room, description, service_type, optional_comment
        )
        await add_message(appeal_id, "user", description)
        if optional_comment:
            await add_message(appeal_id, "user", f"Комментарий: {optional_comment}")

        await send_new_appeal_notification(appeal_id, room, service_type, description, optional_comment)
    finally:
        await conn.close()
    return appeal_id


@router.callback_query(F.data == "service_iron")
async def service_iron(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    service_text = await get_message_template('service_iron') or "🧹 Нужен утюг и гладильная доска"
    await state.update_data(service_text=service_text, service_type="iron")
    add_comment_text = await get_message_template('add_comment') or "💬 Добавить комментарий"
    send_no_comment_text = await get_message_template('send_no_comment') or "✅ Отправить без комментария"
    comment_question = await get_message_template('comment_question') or "Хотите добавить комментарий к заявке?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=add_comment_text, callback_data="add_comment")],
        [InlineKeyboardButton(text=send_no_comment_text, callback_data="send_no_comment")]
    ])
    await callback.message.answer(comment_question, reply_markup=keyboard)

@router.callback_query(F.data == "service_laundry")
async def service_laundry(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    service_text = await get_message_template('service_laundry') or "👕 Услуги прачечной"
    await state.update_data(service_text=service_text, service_type="laundry")
    add_comment_text = await get_message_template('add_comment') or "💬 Добавить комментарий"
    send_no_comment_text = await get_message_template('send_no_comment') or "✅ Отправить без комментария"
    comment_question = await get_message_template('comment_question') or "Хотите добавить комментарий к заявке?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=add_comment_text, callback_data="add_comment")],
        [InlineKeyboardButton(text=send_no_comment_text, callback_data="send_no_comment")]
    ])
    await callback.message.answer(comment_question, reply_markup=keyboard)

@router.callback_query(F.data == "service_technical")
async def service_technical(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tech_ac_text = await get_message_template('tech_ac') or "❄️ Кондиционер"
    tech_wifi_text = await get_message_template('tech_wifi') or "📶 WiFi"
    tech_tv_text = await get_message_template('tech_tv') or "📺 Телевизор"
    tech_other_text = await get_message_template('tech_other') or "🔧 Другое"
    back_services_text = await get_message_template('back_services') or "🔙 Назад"
    service_technical_title = await get_message_template('service_technical') or "Выберите тип технической проблемы:"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tech_ac_text, callback_data="tech_ac")],
        [InlineKeyboardButton(text=tech_wifi_text, callback_data="tech_wifi")],
        [InlineKeyboardButton(text=tech_tv_text, callback_data="tech_tv")],
        [InlineKeyboardButton(text=tech_other_text, callback_data="tech_other")],
        [InlineKeyboardButton(text=back_services_text, callback_data="back_services")]
    ])
    await callback.message.answer(service_technical_title, reply_markup=keyboard)

@router.callback_query(F.data == "tech_ac")
async def tech_ac(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    service_text = await get_message_template('tech_ac') or "❄️ Кондиционер"
    await state.update_data(service_text=service_text, service_type="technical_ac")
    add_comment_text = await get_message_template('add_comment') or "💬 Добавить комментарий"
    send_no_comment_text = await get_message_template('send_no_comment') or "✅ Отправить без комментария"
    comment_question = await get_message_template('comment_question') or "Хотите добавить комментарий к заявке?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=add_comment_text, callback_data="add_comment")],
        [InlineKeyboardButton(text=send_no_comment_text, callback_data="send_no_comment")]
    ])
    await callback.message.answer(comment_question, reply_markup=keyboard)

@router.callback_query(F.data == "tech_wifi")
async def tech_wifi(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    service_text = await get_message_template('tech_wifi') or "📶 WiFi"
    await state.update_data(service_text=service_text, service_type="technical_wifi")
    add_comment_text = await get_message_template('add_comment') or "💬 Добавить комментарий"
    send_no_comment_text = await get_message_template('send_no_comment') or "✅ Отправить без комментария"
    comment_question = await get_message_template('comment_question') or "Хотите добавить комментарий к заявке?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=add_comment_text, callback_data="add_comment")],
        [InlineKeyboardButton(text=send_no_comment_text, callback_data="send_no_comment")]
    ])
    await callback.message.answer(comment_question, reply_markup=keyboard)

@router.callback_query(F.data == "tech_tv")
async def tech_tv(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    service_text = await get_message_template('tech_tv') or "📺 Телевизор"
    await state.update_data(service_text=service_text, service_type="technical_tv")
    add_comment_text = await get_message_template('add_comment') or "💬 Добавить комментарий"
    send_no_comment_text = await get_message_template('send_no_comment') or "✅ Отправить без комментария"
    comment_question = await get_message_template('comment_question') or "Хотите добавить комментарий к заявке?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=add_comment_text, callback_data="add_comment")],
        [InlineKeyboardButton(text=send_no_comment_text, callback_data="send_no_comment")]
    ])
    await callback.message.answer(comment_question, reply_markup=keyboard)

@router.callback_query(F.data == "tech_other")
async def tech_other(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(UserAppeal.waiting_custom_problem)
    custom_problem_prompt = await get_message_template('custom_problem_prompt') or "Опишите проблему:"
    await callback.message.answer(custom_problem_prompt)

@router.callback_query(F.data == "service_restaurant")
async def service_restaurant(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    menu_room_service_text = await get_message_template('menu_room_service') or "📋 Меню рум-сервис"
    menu_restaurant_text = await get_message_template('menu_restaurant') or "🍽 Меню ресторана"
    connect_restaurant_text = await get_message_template('connect_restaurant') or "📞 Соедините с рестораном"
    back_services_text = await get_message_template('back_services') or "🔙 Назад"
    service_restaurant_title = await get_message_template('service_restaurant') or "Выберите услугу ресторана:"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=menu_room_service_text, callback_data="menu_room_service")],
        [InlineKeyboardButton(text=menu_restaurant_text, callback_data="menu_restaurant")],
        [InlineKeyboardButton(text=connect_restaurant_text, callback_data="connect_restaurant")],
        [InlineKeyboardButton(text=back_services_text, callback_data="back_services")]
    ])
    await callback.message.answer(service_restaurant_title, reply_markup=keyboard)

@router.callback_query(F.data == "menu_room_service")
async def menu_room_service(callback: CallbackQuery):
    await callback.answer()
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        menu_path = os.path.join(current_dir, '..', 'menus', 'room_service_menu.pdf')
        menu_path = os.path.abspath(menu_path)

        menu_caption = await get_message_template('menu_room_service_caption') or "📋 Меню рум-сервис"
        menu_unavailable = await get_message_template('menu_unavailable') or "📋 Меню рум-сервис временно недоступно. Обратитесь к администратору."

        if os.path.exists(menu_path):
            menu_file = FSInputFile(menu_path)
            await callback.message.answer_document(menu_file, caption=menu_caption)
        else:
            await callback.message.answer(menu_unavailable)
    except Exception:
        menu_unavailable = await get_message_template('menu_unavailable') or "📋 Меню рум-сервис временно недоступно. Обратитесь к администратору."
        await callback.message.answer(menu_unavailable)

@router.callback_query(F.data == "menu_restaurant")
async def menu_restaurant(callback: CallbackQuery):
    await callback.answer()
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        menu_path = os.path.join(current_dir, '..', 'menus', 'restaurant_menu.pdf')
        menu_path = os.path.abspath(menu_path)

        menu_caption = await get_message_template('menu_restaurant_caption') or "🍽 Меню ресторана"
        menu_unavailable = await get_message_template('restaurant_menu_unavailable') or "🍽 Меню ресторана временно недоступно. Обратитесь к администратору."

        if os.path.exists(menu_path):
            menu_file = FSInputFile(menu_path)
            await callback.message.answer_document(menu_file, caption=menu_caption)
        else:
            await callback.message.answer(menu_unavailable)
    except Exception:
        menu_unavailable = await get_message_template('restaurant_menu_unavailable') or "🍽 Меню ресторана временно недоступно. Обратитесь к администратору."
        await callback.message.answer(menu_unavailable)

@router.callback_query(F.data == "connect_restaurant")
async def connect_restaurant(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    service_text = await get_message_template('connect_restaurant') or "📞 Соедините с рестораном"
    await state.update_data(service_text=service_text, service_type="restaurant_call")
    add_comment_text = await get_message_template('add_comment') or "💬 Добавить комментарий"
    send_no_comment_text = await get_message_template('send_no_comment') or "✅ Отправить без комментария"
    comment_question = await get_message_template('comment_question') or "Хотите добавить комментарий к заявке?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=add_comment_text, callback_data="add_comment")],
        [InlineKeyboardButton(text=send_no_comment_text, callback_data="send_no_comment")]
    ])
    await callback.message.answer(comment_question, reply_markup=keyboard)

@router.callback_query(F.data == "service_other")
async def service_other(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(UserAppeal.waiting_custom_problem)
    custom_question_prompt = await get_message_template('custom_question_prompt') or "Задайте вопрос:"
    await callback.message.answer(custom_question_prompt)

@router.callback_query(F.data == "back_services")
async def back_services(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_service_menu(callback.message, state)

@router.callback_query(F.data == "new_request")
async def new_request(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_service_menu(callback.message, state)


@router.callback_query(F.data == "add_comment")
async def add_comment(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(UserAppeal.waiting_comment)
    add_comment_prompt = await get_message_template('add_comment_prompt') or "Напишите ваш комментарий к заявке:"
    await callback.message.answer(add_comment_prompt)


@router.callback_query(F.data == "send_no_comment")
async def send_no_comment(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await process_service_request(callback, state, None)



@router.message(UserAppeal.waiting_custom_problem)
async def handle_custom_problem(message: Message, state: FSMContext):
    problem_text = message.text.strip()
    await state.update_data(service_text=problem_text, service_type="custom")
    await process_service_request(message, state, None)


@router.message(UserAppeal.waiting_comment)
async def handle_comment(message: Message, state: FSMContext):
    comment_text = message.text.strip()
    await state.update_data(comment=comment_text)
    data = await state.get_data()
    if data.get('is_callback'):
        return
    await process_service_request(message, state, comment_text)

async def process_service_request(event, state: FSMContext, comment: str = None):
    if isinstance(event, CallbackQuery):
        user_id = event.from_user.id
        username = event.from_user.username or str(user_id)
        message = event.message
    else:
        user_id = event.from_user.id
        username = event.from_user.username or str(user_id)
        message = event
    
    data = await state.get_data()
    room = data.get("room", "не указан")
    service_text = data.get("service_text", "")
    service_type = data.get("service_type", "other")

    appeal_id = await create_service_request(user_id, username, room, service_type, service_text, comment)

    await state.update_data(last_appeal_id=appeal_id)

    back_services_text = await get_message_template('back_services') or "🔙 Назад к услугам"
    appeal_created_msg = await get_message_template('appeal_created') or "✅ Ваша заявка отправлена!"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=back_services_text, callback_data="back_services")]
    ])
    await message.answer(appeal_created_msg, reply_markup=keyboard)


@router.callback_query(F.data.startswith("user_reopen:"))
async def user_reopen(callback: CallbackQuery):
    await callback.answer()
    try:
        _, appeal_id = callback.data.split(":")
        appeal_id = int(appeal_id)
    except Exception:
        invalid_appeal_id_msg = await get_message_template('invalid_appeal_id') or "Неправильный ID."
        await callback.message.answer(invalid_appeal_id_msg)
        return

    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("UPDATE appeals SET status = 'new' WHERE id = $1", appeal_id)
    finally:
        await conn.close()

    reopen_message = await get_message_template('reopen_message') or "Мы снова передали ваше обращение администратору ✅"
    await callback.message.answer(reopen_message)


@router.callback_query(F.data.startswith("user_reply:"))
async def user_start_reply(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        _, appeal_id = callback.data.split(":")
        appeal_id = int(appeal_id)
    except Exception:
        invalid_appeal_id_msg = await get_message_template('invalid_appeal_id') or "Неправильный ID."
        await callback.message.answer(invalid_appeal_id_msg)
        return

    await state.update_data(reply_appeal_id=appeal_id)
    await state.set_state(UserAppeal.waiting_reply)

    reply_prompt = await get_message_template('reply_prompt') or "✏️ Напишите ваш ответ администратору:\n\nОтправьте /cancel чтобы отменить ответ."
    await callback.message.answer(reply_prompt)


@router.message(UserAppeal.waiting_reply)
async def user_reply_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    appeal_id = data.get("reply_appeal_id")

    if not appeal_id:
        error_reply_no_id = await get_message_template('error_reply_no_id') or "❌ Ошибка: ID обращения не найден. Попробуйте снова."
        await message.answer(error_reply_no_id)
        await state.clear()
        return

    text = message.text.strip()

    await add_message(appeal_id, "user", text)

    conn = await asyncpg.connect(DB_URL)
    try:
        appeal = await conn.fetchrow("SELECT username, room FROM appeals WHERE id = $1", appeal_id)
        if appeal:
            await conn.execute(
                "UPDATE appeals SET status = 'new', updated_at = NOW() WHERE id = $1 AND status != 'new'",
                appeal_id
            )

            logger.info(f"New user reply on appeal {appeal_id}: {text}")
            logger.info(f"Appeal {appeal_id} status updated to 'new' due to user reply")

            await send_user_message_notification(appeal_id, appeal['username'], appeal['room'], text)
    finally:
        await conn.close()

    reply_sent_msg = await get_message_template('reply_sent') or "✅ Ваш ответ отправлен администратору!"
    await message.answer(reply_sent_msg)
    await state.clear()


@dp.errors()
async def global_error_handler(event, data):
    exception = data.get('exception')
    logger.exception("Ошибка при обработке апдейта: %s", exception)


async def check_message_queue():
    while True:
        try:
            conn = await asyncpg.connect(DB_URL)
            try:
                pending_messages = await conn.fetch(
                    """SELECT id, user_id, message, appeal_id, created_at 
                       FROM pending_admin_messages 
                       WHERE sent = FALSE 
                       AND created_at <= NOW() - INTERVAL '2 seconds'
                       ORDER BY created_at LIMIT 10"""
                )
                
                bot_info = await bot.get_me()
                
                for msg in pending_messages:
                    try:
                        if msg['user_id'] == bot_info.id:
                            logger.warning(f"Skipping message to bot itself (ID: {msg['user_id']})")
                            await conn.execute(
                                "UPDATE pending_admin_messages SET sent = TRUE WHERE id = $1",
                                msg['id']
                            )
                            continue

                        await conn.execute(
                            "UPDATE pending_admin_messages SET sent = TRUE WHERE id = $1",
                            msg['id']
                        )

                        message_text = msg['message']
                        reply_markup = None

                        if msg['appeal_id']:
                            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                            buttons = []

                            if 'Ответ администратора' in message_text or 'Ваше обращение' in message_text:
                                reply_button_text = "✏️ Ответить"
                                buttons.append([InlineKeyboardButton(text=reply_button_text, callback_data=f"user_reply:{msg['appeal_id']}")])

                            if 'выполнено ✅' in message_text:
                                reopen_button_text = "❌ Не решено"
                                buttons.append([InlineKeyboardButton(text=reopen_button_text, callback_data=f"user_reopen:{msg['appeal_id']}")])

                            if buttons:
                                reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)

                        await bot.send_message(
                            chat_id=msg['user_id'],
                            text=message_text,
                            reply_markup=reply_markup,
                            disable_notification=False
                        )

                        logger.info(f"Sent admin message to user {msg['user_id']}")
                        
                    except Exception as e:
                        logger.error(f"Failed to send message to user {msg['user_id']}: {e}")

                        if "Forbidden: bots can't send messages to bots" in str(e):
                            logger.warning(f"User {msg['user_id']} blocked the bot or is a bot - marking as sent")
                            try:
                                await conn.execute(
                                    "UPDATE pending_admin_messages SET sent = TRUE WHERE id = $1",
                                    msg['id']
                                )
                            except Exception as rollback_error:
                                logger.error(f"Failed to mark message as sent: {rollback_error}")
                        else:
                            try:
                                await conn.execute(
                                    "UPDATE pending_admin_messages SET sent = FALSE WHERE id = $1",
                                    msg['id']
                                )
                            except Exception as rollback_error:
                                logger.error(f"Failed to rollback message status: {rollback_error}")
                        
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"Error checking message queue: {e}")
        
        await asyncio.sleep(5)

async def main():
    logger.info("Инициализация БД...")
    await init_db()
    await init_message_templates()
    await init_settings()

    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_admin_messages (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                message TEXT NOT NULL,
                appeal_id INTEGER,
                sent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    finally:
        await conn.close()

    logger.info("Запуск polling и проверки очереди сообщений...")
    asyncio.create_task(check_message_queue())

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")