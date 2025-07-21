from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db import SessionLocal, User, Answer
from main import LOCALES
from sqlalchemy import select, func, desc, and_, update
from keyboards.menu import get_menu_keyboard
from datetime import datetime, date

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
    text = "Выберите язык / Choose your language:"
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

    kb = InlineKeyboardBuilder()
    kb.button(text=locale.get("play_btn", "🎮 Играть"), callback_data="menu_play")
    kb.button(text=locale.get("stats_btn", "📊 Моя статистика"), callback_data="menu_stats")
    kb.button(text=locale.get("rating_btn", "🏆 Рейтинг дня"), callback_data="menu_rating")
    kb.adjust(1)

    await callback.message.answer(locale.get("menu", "Выберите действие:"), reply_markup=kb.as_markup())
    await callback.answ
er()
    await state.clear()


@router.callback_query(F.data == "menu_play")
async def menu_play(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        user = result.scalar_one_or_none()
        lang = user.lang if user else 'ru'
    locale = LOCALES.get(lang, LOCALES['ru'])
    await callback.message.answer(locale.get('play_soon', 'Игра скоро будет!'))
    await callback.answer()


ACHIEVEMENTS = [
    {"emoji": "🧠", "check": lambda user: user.streak >= 5, "name": "Киноман"},
    {"emoji": "🌍", "check": lambda user: user.games_played >= 10, "name": "Исследователь"},
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
                    Answer.is_correct == True,
                    Answer.date >= datetime.combine(today, datetime.min.time()),
                    Answer.date <= datetime.combine(today, datetime.max.time()),
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
