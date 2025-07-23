from aiogram import Router, F
from aiogram.types import CallbackQuery, InputFile
from db import SessionLocal, User, Answer, QuestionSent
from sqlalchemy import select, and_
import json
import os
import random
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, date


router = Router()


def load_questions(topic, lang):
    fname = f"data/{topic}_{lang}.json"
    if not os.path.exists(fname):
        return []
    with open(fname, encoding="utf-8") as f:
        return json.load(f)


def get_quiz_keyboard(options, topic):
    kb = InlineKeyboardBuilder()
    for opt in options:
        kb.button(text=opt, callback_data=f"quiz_answer_{topic}_{opt}")
    kb.adjust(2)
    return kb.as_markup()


def get_question_by_option(option, topic, lang):
    questions = load_questions(topic, lang)
    for q in questions:
        if option in q['options']:
            return q
    return None


def filter_unsent_questions(questions, sent_ids):
    return [q for q in questions if q['id'] not in sent_ids]


# Списки реакций (эмодзи и GIF-ссылки)
CORRECT_REACTIONS = [
    "🎉", "🧠", "😎", "https://media.giphy.com/media/111ebonMs90YLu/giphy.gif", "https://media.giphy.com/media/26ufdipQqU2lhNA4g/giphy.gif"
]
WRONG_REACTIONS = [
    "😢", "😵", "https://media.giphy.com/media/3o6ZtaO9BZHcOjmErm/giphy.gif", "https://media.giphy.com/media/l2JehQ2GitHGdVG9y/giphy.gif"
]

# Путь к универсальному баннеру победителя
WIN_BANNER_PATH = 'data/images/win_banner.jpg'


@router.callback_query(F.data == "menu_play")
async def start_quiz(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        user = result.scalar_one_or_none()
        lang = user.lang if user else 'ru'
        topic = random.choice(['movies', 'cities'])
        questions = load_questions(topic, lang)
        # Получаем id уже отправленных вопросов
        sent_result = await session.execute(
            select(QuestionSent.question_id).where(
                QuestionSent.user_id == user.id,
                QuestionSent.topic == topic
            )
        )
        sent_ids = [row[0] for row in sent_result.fetchall()]
        available = filter_unsent_questions(questions, sent_ids)
        if not available:
            await callback.message.answer("Вопросы закончились! Попробуйте позже.")
            await callback.answer()
            return
        q = random.choice(available)
        # Сохраняем отправленный вопрос
        qs = QuestionSent(
            user_id=user.id,
            question_id=q['id'],
            topic=topic,
            sent_at=datetime.now()
        )
        session.add(qs)
        await session.commit()
    text = f"<b>{q['question']}</b>"
    img_path = os.path.join('data', 'images', q['image'])
    kb = get_quiz_keyboard(q['options'], topic)
    if os.path.exists(img_path):
        photo = InputFile(img_path)
        await callback.message.answer_photo(
            photo, caption=text, reply_markup=kb
        )
    else:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("quiz_answer_"))
async def answer_quiz(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data.replace("quiz_answer_", "")
    if "_" not in data:
        await callback.message.answer("Ошибка данных ответа.")
        await callback.answer()
        return
    topic, chosen = data.split("_", 1)
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        user = result.scalar_one_or_none()
        lang = user.lang if user else 'ru'
        q = get_question_by_option(chosen, topic, lang)
        if not q:
            await callback.message.answer("Вопрос не найден.")
            await callback.answer()
            return
        today = date.today()
        answer_exists = await session.execute(
            select(Answer).where(
                and_(
                    Answer.user_id == user.id,
                    Answer.question_id == q['id'],
                    Answer.topic == topic,
                    Answer.date >= datetime.combine(today, datetime.min.time()),
                    Answer.date <= datetime.combine(today, datetime.max.time()),
                )
            )
        )
        if answer_exists.scalar_one_or_none():
            await callback.message.answer("Вы уже отвечали на этот вопрос сегодня!")
            await callback.answer()
            return
        is_correct = (chosen == q['answer'])
        answer = Answer(
            user_id=user.id,
            question_id=q['id'],
            topic=topic,
            is_correct=is_correct,
            date=datetime.now()
        )
        session.add(answer)
        if is_correct:
            user.score += 1
            user.streak += 1
        else:
            user.streak = 0
        user.games_played += 1
        await session.commit()
    if is_correct:
        msg = "✅ Верно!\n"
        reaction = random.choice(CORRECT_REACTIONS)
    else:
        msg = (
            f"❌ Неверно. Правильный ответ: <b>{q['answer']}</b>\n"
        )
        reaction = random.choice(WRONG_REACTIONS)
    if q.get('fact'):
        msg += f"\nℹ️ {q['fact']}"
    # Добавляем реакцию (эмодзи или GIF)
    if reaction.startswith("http"):
        await callback.message.answer(msg)
        await callback.message.answer_animation(reaction)
    else:
        msg += f"\n{reaction}"
        await callback.message.answer(msg)
    # Отправляем баннер победителя, если ответ верный
    if is_correct and os.path.exists(WIN_BANNER_PATH):
        await callback.message.answer_photo(InputFile(WIN_BANNER_PATH), caption="🏆 Поздравляем с победой!")
    await callback.answer()
