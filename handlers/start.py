from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db import SessionLocal, User, Answer
from main import LOCALES
from sqlalchemy import select, func, desc, and_, update
from keyboards.menu import get_reply_menu_keyboard
from datetime import datetime, date, timedelta
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db import get_or_create_user
from urllib.parse import unquote
import os

router = Router()

LANGS = [
    ("ru", "🇷🇺 Русский"),
    ("en", "🇬🇧 English"),
]


def get_lang_keyboard():
    kb = InlineKeyboardBuilder()
    for code, label in LANGS:
        kb.button(text=label, callback_data=f"lang_{code}")
    return kb.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message):
    # Обработка реферального параметра
    referrer_id = None
    if message.text and ' ' in message.text:
        param = message.text.split(' ', 1)[1]
        if param.startswith('ref_'):
            try:
                referrer_id = int(param.replace('ref_', ''))
            except Exception:
                referrer_id = None
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            # Новый пользователь — сохраняем пригласившего
            user = User(tg_id=message.from_user.id, username=message.from_user.username, referrer_id=referrer_id)
            session.add(user)
            await session.commit()
            if referrer_id:
                ref_result = await session.execute(select(User).where(User.tg_id == referrer_id))
                ref_user = ref_result.scalar_one_or_none()
                if ref_user:
                    ref_user.referrals_count = (ref_user.referrals_count or 0) + 1
                    await session.commit()
    welcome_img = 'data/images/welcome.jpg'
    text = "👋 Добро пожаловать в GuessShotBot!\n\nВыберите язык / Choose your language:"
    if os.path.exists(welcome_img):
        await message.answer_photo(InputFile(welcome_img), caption=text)
    else:
        await message.answer(text)
    await message.answer(text, reply_markup=get_lang_keyboard())


@router.callback_query(F.data.startswith("lang_"))
async def lang_chosen(callback: CallbackQuery, state: FSMContext, data: dict):
    lang = callback.data.split("_")[1]

    async with SessionLocal() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        user.lang = lang
        await session.commit()

    locales = data["locales"]
    locale = locales.get(lang, locales.get("ru", {}))

    # Отправляем обычную клавиатуру меню
    reply_kb = get_reply_menu_keyboard(lang)
    await callback.message.answer(
        locale.get("menu", "Выберите действие:"), reply_markup=reply_kb
    )
    await callback.answer()
    await state.clear()


# Обработка текстовых кнопок главного меню (ReplyKeyboard)
@router.message()
async def handle_menu_buttons(message: Message):
    user_id = message.from_user.id
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        user = result.scalar_one_or_none()
        lang = user.lang if user else 'ru'
    locale = LOCALES.get(lang, LOCALES['ru'])
    text = message.text.strip()
    if text == locale.get('play_btn', '🎬 Играть'):
        # Имитация нажатия на inline-кнопку "Играть"
        await message.answer(locale.get('play_soon', 'Игра скоро будет!'))
    elif text == locale.get('stats_btn', '📊 Моя статистика'):
        # Имитация нажатия на inline-кнопку "Статистика"
        await menu_stats_message(message, user, lang)
    elif text == locale.get('rating_btn', '🏆 Ежедневный рейтинг'):
        # Имитация нажатия на inline-кнопку "Рейтинг дня"
        await menu_rating_message(message, user, lang)


# Вспомогательные функции для вывода статистики и рейтинга по текстовой команде
async def menu_stats_message(message: Message, user, lang):
    locale = LOCALES.get(lang, LOCALES['ru'])
    async with SessionLocal() as session:
        user.no_win_streak = get_no_win_streak(user, session)
        user.answer_streak = get_answer_streak(user, session)
    medals = user.medals if user and user.medals else ''
    new_achievements = []
    ach_texts = []
    for ach in ACHIEVEMENTS:
        if ach["emoji"] not in medals and ach["check"](user):
            medals += ach["emoji"] + ' '
            new_achievements.append(ach["emoji"])
        if ach["emoji"] in medals:
            key = 'ach_brain' if ach["emoji"] == '🧠' else 'ach_explorer'
            ach_texts.append(locale.get(key, ach["name"]))
    if '🥇' in medals:
        ach_texts.append(locale.get('winner_medal', '🥇 Winner of the Day'))
    if new_achievements:
        async with SessionLocal() as session:
            await session.execute(
                update(User).where(User.id == user.id).values(medals=medals)
            )
            await session.commit()
    stats = (
        f"{locale.get('your_score', 'Ваш счёт')}: <b>{user.score if user else 0}</b>\n"
        f"{locale.get('your_streak', 'Серия побед')}: <b>{user.streak if user else 0}</b>\n"
        f"{locale.get('games_played', 'Игр сыграно')}: <b>{user.games_played if user else 0}</b>\n"
        f"{locale.get('achievements', 'Ачивки')}: {'; '.join(ach_texts) if ach_texts else '-'}"
    )
    await message.answer(stats, parse_mode='HTML')


async def menu_rating_message(message: Message, user, lang):
    locale = LOCALES.get(lang, LOCALES['ru'])
    today = date.today()
    async with SessionLocal() as session:
        scores_result = await session.execute(
            select(
                Answer.user_id,
                func.count().label('score')
            ).where(
                and_(
                    Answer.is_correct,
                    Answer.date >= datetime.combine(
                        today, datetime.min.time()
                    ),
                    Answer.date <= datetime.combine(
                        today, datetime.max.time()
                    ),
                )
            ).group_by(Answer.user_id).order_by(desc('score')).limit(5)
        )
        scores = scores_result.fetchall()
        if not scores:
            await message.answer(locale.get('no_rating_today', 'Сегодня ещё нет победителей!'))
            return
        user_ids = [row[0] for row in scores]
        users_result = await session.execute(select(User).where(User.id.in_(user_ids)))
        users_dict = {u.id: u for u in users_result.scalars()}
        top1_id = scores[0][0]
        top1_user = users_dict[top1_id]
        if '🥇' not in (top1_user.medals or ''):
            new_medals = (top1_user.medals or '') + '🥇 '
            await session.execute(
                update(User).where(User.id == top1_id).values(medals=new_medals)
            )
            await session.commit()
        lines = []
        for idx, (uid, score) in enumerate(scores, 1):
            medal = '🥇 ' if idx == 1 else ''
            uname = users_dict[uid].username or f"id{users_dict[uid].tg_id}"
            lines.append(
                f"{medal}{idx}. {uname}: <b>{score}</b>"
            )
        text = (
            f"{locale.get('rating_today', 'Рейтинг дня')}\n\n" + "\n".join(lines)
        )
        await message.answer(text, parse_mode='HTML')


ACHIEVEMENTS = [
    {"emoji": "🧠", "check": lambda user: user.streak >= 5, "name": "Киноман"},
    {"emoji": "🌍", "check": lambda user: user.games_played >= 10, "name": "Исследователь"},
    {"emoji": "🏅", "check": lambda user: user.streak >= 10, "name": "Мастер интуиции"},
    {"emoji": "🔥", "check": lambda user: (user.score or 0) > 0 and (user.games_played or 0) > 0 and (user.score == 1), "name": "Новичок в деле"},
    {"emoji": "🐢", "check": lambda user: hasattr(user, 'no_win_streak') and user.no_win_streak >= 3, "name": "Терпеливый"},
    {"emoji": "📆", "check": lambda user: hasattr(user, 'answer_streak') and user.answer_streak >= 7, "name": "Верный игрок"},
    {"emoji": "📣", "check": lambda user: (user.referrals_count or 0) >= 5, "name": "Амбассадор"},
    {"emoji": "💪", "check": lambda user: hasattr(user, 'answer_streak') and user.answer_streak >= 7, "name": "Железная воля"},
]


@router.callback_query(F.data == "menu_stats")
async def menu_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        user = result.scalar_one_or_none()
        lang = user.lang if user else 'ru'
    locale = LOCALES.get(lang, LOCALES['ru'])
    async with SessionLocal() as session:
        user.no_win_streak = get_no_win_streak(user, session)
        user.answer_streak = get_answer_streak(user, session)
    medals = user.medals if user and user.medals else ''
    # Проверяем ачивки
    new_achievements = []
    ach_texts = []
    for ach in ACHIEVEMENTS:
        if ach["emoji"] not in medals and ach["check"](user):
            medals += ach["emoji"] + ' '
            new_achievements.append(ach["emoji"])
        if ach["emoji"] in medals:
            key = 'ach_brain' if ach["emoji"] == '🧠' else 'ach_explorer'
            ach_texts.append(locale.get(key, ach["name"]))
    # Медалька победителя дня
    if '🥇' in medals:
        ach_texts.append(locale.get('winner_medal', '🥇 Winner of the Day'))
    if new_achievements:
        async with SessionLocal() as session:
            await session.execute(
                update(User).where(User.id == user.id).values(medals=medals)
            )
            await session.commit()
    stats = (
        f"{locale.get('your_score', 'Ваш счёт')}: <b>{user.score if user else 0}</b>\n"
        f"{locale.get('your_streak', 'Серия побед')}: <b>{user.streak if user else 0}</b>\n"
        f"{locale.get('games_played', 'Игр сыграно')}: <b>{user.games_played if user else 0}</b>\n"
        f"{locale.get('achievements', 'Ачивки')}: {'; '.join(ach_texts) if ach_texts else '-'}"
    )
    await callback.message.answer(stats)
    await callback.answer()


@router.callback_query(F.data == "menu_rating")
async def menu_rating(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        user = result.scalar_one_or_none()
        lang = user.lang if user else 'ru'
        locale = LOCALES.get(lang, LOCALES['ru'])
        today = date.today()
        # Считаем очки за сегодня
        scores_result = await session.execute(
            select(
                Answer.user_id,
                func.count().label('score')
            ).where(
                and_(
                    Answer.is_correct,
                    Answer.date >= datetime.combine(
                        today, datetime.min.time()
                    ),
                    Answer.date <= datetime.combine(
                        today, datetime.max.time()
                    ),
                )
            ).group_by(Answer.user_id).order_by(desc('score')).limit(10)
        )
        scores = scores_result.fetchall()
        if not scores:
            await callback.message.answer(locale.get('no_rating_today', 'Сегодня ещё нет победителей!'))
            await callback.answer()
            return
        # Получаем пользователей
        user_ids = [row[0] for row in scores]
        users_result = await session.execute(select(User).where(User.id.in_(user_ids)))
        users_dict = {u.id: u for u in users_result.scalars()}
        # Присваиваем медальку топ-1
        top1_id = scores[0][0]
        top1_user = users_dict[top1_id]
        if '🥇' not in (top1_user.medals or ''):
            new_medals = (top1_user.medals or '') + '🥇 '
            await session.execute(
                update(User).where(User.id == top1_id).values(medals=new_medals)
            )
            await session.commit()
        lines = []
        for idx, (uid, score) in enumerate(scores, 1):
            medal = '🥇 ' if idx == 1 else ''
            uname = users_dict[uid].username or f"id{users_dict[uid].tg_id}"
            lines.append(f"{medal}{idx}. {uname}: <b>{score}</b>")
        text = f"{locale.get('rating_today', 'Рейтинг дня')}\n\n" + "\n".join(lines)
        await callback.message.answer(text)
    await callback.answer()


@router.message(Command("stats"))
async def stats_command(message: Message):
    user_id = message.from_user.id
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        user = result.scalar_one_or_none()
        lang = user.lang if user else 'ru'
    await menu_stats_message(message, user, lang)


@router.message(Command("rating"))
async def rating_command(message: Message):
    user_id = message.from_user.id
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        user = result.scalar_one_or_none()
        lang = user.lang if user else 'ru'
    await menu_rating_message(message, user, lang)


@router.message(Command("profile"))
async def profile_command(message: Message):
    user_id = message.from_user.id
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        user = result.scalar_one_or_none()
        lang = user.lang if user else 'ru'
    await send_profile(message, user, lang)

# Обработка текстовой кнопки "👤 Профиль"
@router.message()
async def handle_profile_button(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    locale = LOCALES.get('ru', LOCALES['ru'])
    if text == locale.get('profile_btn', '👤 Профиль'):
        async with SessionLocal() as session:
            result = await session.execute(
                select(User).where(User.tg_id == user_id)
            )
            user = result.scalar_one_or_none()
            lang = user.lang if user else 'ru'
        await send_profile(message, user, lang)

async def send_profile(message: Message, user, lang):
    locale = LOCALES.get(lang, LOCALES['ru'])
    if not user:
        await message.answer("Профиль не найден.")
        return
    async with SessionLocal() as session:
        user.no_win_streak = get_no_win_streak(user, session)
        user.answer_streak = get_answer_streak(user, session)
    # Формируем профиль
    username = user.username or f"id{user.tg_id}"
    first_seen = user.created_at.strftime('%d.%m.%Y') if hasattr(user, 'created_at') and user.created_at else '-'
    total_games = user.games_played or 0
    wins = user.score or 0
    losses = total_games - wins if total_games > wins else 0
    streak = user.streak or 0
    lang_display = 'Русский' if lang == 'ru' else 'English'
    # Ачивки с описанием
    medals = user.medals if user and user.medals else ''
    ach_texts = []
    for ach in ACHIEVEMENTS:
        if ach["emoji"] in medals or ach["check"](user):
            key = 'ach_brain' if ach["emoji"] == '🧠' else 'ach_explorer'
            if ach["emoji"] == '🏅':
                key = 'ach_master'
            elif ach["emoji"] == '🐢':
                key = 'ach_turtle'
            elif ach["emoji"] == '🔥':
                key = 'ach_newbie'
            elif ach["emoji"] == '📆':
                key = 'ach_loyal'
            ach_texts.append(f"{ach['emoji']} {locale.get(key, ach['name'])}")
    if '🥇' in medals:
        ach_texts.append(locale.get('winner_medal', '🥇 Winner of the Day'))
    ach_str = '\n'.join(ach_texts) if ach_texts else '-'
    profile = (
        f"<b>👤 Профиль</b>\n"
        f"Имя: <b>{username}</b>\n"
        f"Язык: <b>{lang_display}</b>\n"
        f"Первый заход: <b>{first_seen}</b>\n"
        f"Всего игр: <b>{total_games}</b>\n"
        f"Победы: <b>{wins}</b> / Поражения: <b>{losses}</b>\n"
        f"Серия побед: <b>{streak}</b>\n"
        f"Ачивки:\n{ach_str}\n"
        f"Приглашённых: <b>{user.referrals_count or 0}</b>\n"
        f"Ваша ссылка: https://t.me/guessshot_test_bot?start=ref_{user.tg_id}\n"
    )
    await message.answer(profile, parse_mode='HTML')


@router.message(Command("help"))
async def help_command(message: Message):
    text = (
        "GuessShotBot — викторина с фото-вопросами!\n\n"
        "Каждый день 2 вопроса: кадр из фильма и город.\n"
        "Отвечайте, набирайте очки, попадайте в рейтинг дня!\n\n"
        "Команды:\n"
        "/start — старт и выбор языка\n"
        "/stats — ваша статистика и ачивки\n"
        "/rating — топ-5 игроков дня\n"
        "/help — правила игры\n\n"
        "Используйте кнопки меню для быстрого доступа."
    )
    await message.answer(text)


@router.message(Command("history"))
async def history_command(message: Message):
    user_id = message.from_user.id
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return
        answers_result = await session.execute(
            select(Answer).where(Answer.user_id == user.id).order_by(Answer.date.desc()).limit(5)
        )
        answers = answers_result.scalars().all()
    if not answers:
        await message.answer("Нет истории ответов.")
        return
    lines = []
    for ans in answers:
        date_str = ans.date.strftime('%d.%m.%Y %H:%M')
        status = '✅' if ans.is_correct else '❌'
        lines.append(f"{date_str} | {ans.topic} | {status} | {getattr(ans, 'chosen', '-')}")
    text = "<b>Последние 5 ответов:</b>\n" + "\n".join(lines)
    await message.answer(text, parse_mode='HTML')

# Для новых ачивок потребуется вычислять no_win_streak и answer_streak для пользователя
# Добавляю функции для подсчёта этих параметров

def get_no_win_streak(user, session):
    # Считает дни подряд без побед (последние дни)
    from sqlalchemy import func
    today = date.today()
    streak = 0
    for i in range(3):
        day = today - timedelta(days=i)
        res = session.execute(
            select(Answer).where(
                Answer.user_id == user.id,
                func.date(Answer.date) == day,
            )
        )
        answers = res.scalars().all()
        if not answers:
            break
        if any(a.is_correct for a in answers):
            break
        streak += 1
    return streak

def get_answer_streak(user, session):
    # Считает дни подряд с ответами (последние дни)
    from sqlalchemy import func
    today = date.today()
    streak = 0
    for i in range(7):
        day = today - timedelta(days=i)
        res = session.execute(
            select(Answer).where(
                Answer.user_id == user.id,
                func.date(Answer.date) == day,
            )
        )
        answers = res.scalars().all()
        if answers:
            streak += 1
        else:
            break
    return streak

ADMIN_CHAT_ID = 5900895276

class AdminStates(StatesGroup):
    menu = State()
    upload_question = State()
    input_topic = State()
    input_question = State()
    input_options = State()
    input_answer = State()
    input_fact = State()
    input_photo = State()
    confirm = State()
    stats = State()
    clear = State()

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📥 Загрузить вопрос")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🧹 Очистить")],
        [KeyboardButton(text="↩️ Назад")],
    ],
    resize_keyboard=True
)

@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        await message.answer("Нет доступа.")
        return
    await message.answer("🛠 <b>Админ-панель</b>\nВыберите действие:", reply_markup=admin_kb, parse_mode='HTML')
    await state.set_state(AdminStates.menu)

@router.message(AdminStates.menu)
async def admin_menu_handler(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "📥 Загрузить вопрос":
        await message.answer("Выберите тему (movies, cities, music, sport):")
        await state.set_state(AdminStates.input_topic)
    elif text == "📊 Статистика":
        await message.answer("Введите тему для просмотра вопросов (movies, cities, music, sport):")
        await state.set_state(AdminStates.stats)
    elif text == "🧹 Очистить":
        await message.answer("Очистка (в разработке)")
        # await state.set_state(AdminStates.clear)
    elif text == "↩️ Назад":
        await message.answer("Выход из админ-панели.", reply_markup=get_reply_menu_keyboard('ru'))
        await state.clear()
    else:
        await message.answer("Неизвестная команда.")

@router.message(AdminStates.stats)
async def admin_stats_topic(message: Message, state: FSMContext):
    topic = message.text.strip()
    lang = 'ru'  # Можно добавить выбор языка
    file_path = f"data/{topic}_{lang}.json"
    import os, json
    if not os.path.exists(file_path):
        await message.answer(f"Файл {file_path} не найден.")
        await state.set_state(AdminStates.menu)
        return
    with open(file_path, encoding='utf-8') as f:
        questions = json.load(f)
    if not questions:
        await message.answer("Вопросов нет.")
        await state.set_state(AdminStates.menu)
        return
    lines = [f"{q['id']}. {q['question']}" for q in questions]
    text = f"<b>Вопросы по теме {topic}:</b>\n" + '\n'.join(lines)
    await message.answer(text, parse_mode='HTML')
    await state.set_state(AdminStates.menu)

@router.message(AdminStates.input_topic)
async def admin_input_topic(message: Message, state: FSMContext):
    topic = message.text.strip()
    await state.update_data(topic=topic)
    await message.answer("Введите текст вопроса:")
    await state.set_state(AdminStates.input_question)

@router.message(AdminStates.input_question)
async def admin_input_question(message: Message, state: FSMContext):
    await state.update_data(question=message.text.strip())
    await message.answer("Введите варианты ответа через запятую:")
    await state.set_state(AdminStates.input_options)

@router.message(AdminStates.input_options)
async def admin_input_options(message: Message, state: FSMContext):
    options = [opt.strip() for opt in message.text.split(',') if opt.strip()]
    await state.update_data(options=options)
    await message.answer("Введите правильный ответ:")
    await state.set_state(AdminStates.input_answer)

@router.message(AdminStates.input_answer)
async def admin_input_answer(message: Message, state: FSMContext):
    await state.update_data(answer=message.text.strip())
    await message.answer("Введите интересный факт (или '-' если не нужно):")
    await state.set_state(AdminStates.input_fact)

@router.message(AdminStates.input_fact)
async def admin_input_fact(message: Message, state: FSMContext):
    fact = message.text.strip()
    if fact == '-':
        fact = ''
    await state.update_data(fact=fact)
    await message.answer("Отправьте фото для вопроса:")
    await state.set_state(AdminStates.input_photo)

@router.message(AdminStates.input_photo)
async def admin_input_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("Пожалуйста, отправьте фото.")
        return
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_path = file.file_path
    # Сохраняем фото локально
    img_name = f"admin_{photo.file_id}.jpg"
    img_path = f"data/images/{img_name}"
    await message.bot.download(file, destination=img_path)
    await state.update_data(image=img_name)
    data = await state.get_data()
    # Сохраняем вопрос в файл
    topic = data['topic']
    lang = 'ru'  # Можно добавить выбор языка
    file_path = f"data/{topic}_{lang}.json"
    import json, os
    if os.path.exists(file_path):
        with open(file_path, encoding='utf-8') as f:
            questions = json.load(f)
    else:
        questions = []
    new_id = max([q['id'] for q in questions], default=0) + 1
    question = {
        'id': new_id,
        'question': data['question'],
        'options': data['options'],
        'answer': data['answer'],
        'image': img_name,
        'fact': data['fact']
    }
    questions.append(question)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    await message.answer(f"Вопрос успешно добавлен в {file_path}!", reply_markup=admin_kb)
    await state.set_state(AdminStates.menu)


class FeedbackStates(StatesGroup):
    waiting_feedback = State()

@router.message()
async def handle_feedback_button(message: Message, state: FSMContext):
    text = message.text.strip()
    locale = LOCALES.get('ru', LOCALES['ru'])
    if text == locale.get('feedback_btn', '💬 Отзывы и предложения'):
        await message.answer(
            "Напишите ваш отзыв или идею — мы учтём! Сообщение будет передано администратору."
        )
        await state.set_state(FeedbackStates.waiting_feedback)

@router.message(FeedbackStates.waiting_feedback)
async def process_feedback(message: Message, state: FSMContext):
    # Пересылаем сообщение админу
    await message.copy_to(ADMIN_CHAT_ID)
    await message.answer("Спасибо за ваш отзыв! Он отправлен администратору.")
    await state.clear()

@router.message(Command("achievements"))
async def achievements_command(message: Message):
    await show_achievements_leaders(message)

@router.message()
async def handle_achievements_button(message: Message):
    text = message.text.strip()
    locale = LOCALES.get('ru', LOCALES['ru'])
    if text == locale.get('achievements_btn', '🏅 Ачивки-лидеры'):
        await show_achievements_leaders(message)

async def show_achievements_leaders(message: Message):
    async with SessionLocal() as session:
        users_result = await session.execute(select(User))
        users = users_result.scalars().all()
        # Считаем количество ачивок у каждого
        leaderboard = []
        for user in users:
            medals = (user.medals or '').strip().split()
            if not medals:
                continue
            # Для сортировки по дате последней ачивки ищем последнюю дату победы
            last_ach_date = user.created_at or datetime.min
            answers_result = await session.execute(
                select(Answer).where(Answer.user_id == user.id).order_by(Answer.date.desc())
            )
            answers = answers_result.scalars().all()
            if answers:
                last_ach_date = answers[0].date
            leaderboard.append({
                'user': user,
                'medals': medals,
                'count': len(medals),
                'last_ach_date': last_ach_date
            })
        # Сортировка: по количеству ачивок, затем по дате последней ачивки (убыв.)
        leaderboard.sort(key=lambda x: (-x['count'], -x['last_ach_date'].timestamp()))
        top = leaderboard[:10]
        if not top:
            await message.answer('Пока нет лидеров по ачивкам.')
            return
        lines = []
        for idx, entry in enumerate(top, 1):
            user = entry['user']
            medals = ' '.join(entry['medals'])
            uname = user.username or f"id{user.tg_id}"
            lines.append(f"{idx}. <b>{uname}</b> — {medals} ({entry['count']})")
        text = '<b>🏅 Топ-10 по ачивкам:</b>\n' + '\n'.join(lines)
        await message.answer(text, parse_mode='HTML')

@router.message(Command("weekly"))
async def weekly_rating(message: Message):
    await show_season_rating(message, period='week')

@router.message(Command("monthly"))
async def monthly_rating(message: Message):
    await show_season_rating(message, period='month')

async def show_season_rating(message: Message, period='week'):
    user_id = message.from_user.id
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == user_id))
        user = result.scalar_one_or_none()
        lang = user.lang if user else 'ru'
        locale = LOCALES.get(lang, LOCALES['ru'])
        today = date.today()
        if period == 'week':
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            title = locale.get('weekly_rating', '🏆 Рейтинг недели')
        else:
            start = today.replace(day=1)
            end = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            title = locale.get('monthly_rating', '🏆 Рейтинг месяца')
        scores_result = await session.execute(
            select(
                Answer.user_id,
                func.count().label('score')
            ).where(
                and_(
                    Answer.is_correct,
                    Answer.date >= datetime.combine(start, datetime.min.time()),
                    Answer.date <= datetime.combine(end, datetime.max.time()),
                )
            ).group_by(Answer.user_id).order_by(desc('score')).limit(10)
        )
        scores = scores_result.fetchall()
        if not scores:
            await message.answer(locale.get('no_rating_today', 'Сегодня ещё нет победителей!'))
            return
        user_ids = [row[0] for row in scores]
        users_result = await session.execute(select(User).where(User.id.in_(user_ids)))
        users_dict = {u.id: u for u in users_result.scalars()}
        # Ачивки за топ-3
        for idx, (uid, score) in enumerate(scores[:3], 1):
            top_user = users_dict[uid]
            medal = {1: '🥇', 2: '🥈', 3: '🥉'}.get(idx)
            if medal and (not top_user.medals or medal not in top_user.medals):
                new_medals = (top_user.medals or '') + f'{medal} '
                await session.execute(update(User).where(User.id == top_user.id).values(medals=new_medals))
                await session.commit()
        lines = []
        for idx, (uid, score) in enumerate(scores, 1):
            medal = {1: '🥇', 2: '🥈', 3: '🥉'}.get(idx, '')
            uname = users_dict[uid].username or f"id{users_dict[uid].tg_id}"
            lines.append(f"{medal}{idx}. {uname}: <b>{score}</b>")
        text = f"{title}\n\n" + "\n".join(lines)
        await message.answer(text, parse_mode='HTML')
