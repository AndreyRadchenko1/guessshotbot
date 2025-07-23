import asyncio
import logging
import os
import json
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from db import init_db, SessionLocal, User, QuestionSent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from sqlalchemy import select
from datetime import datetime
from aiogram.types import InputFile
import random

# Загрузка токена из переменных окружения или config.py
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    from config import BOT_TOKEN as CONFIG_TOKEN
    BOT_TOKEN = CONFIG_TOKEN

# Настройка логирования
logging.basicConfig(level=logging.INFO)


# Глобальный объект локалей
LOCALES = {}


def get_locales():
    locales = {}
    for lang in ['ru', 'en']:
        path = os.path.join('locales', f'{lang}.json')
        try:
            with open(path, encoding='utf-8') as f:
                locales[lang] = json.load(f)
        except Exception as e:
            logging.error(f'Failed to load locale {lang}: {e}')
            locales[lang] = {}
    return locales


# Регистрация роутеров (handlers)
def register_routers(dp: Dispatcher):
    from handlers import start, quiz
    dp.include_router(start.router)
    dp.include_router(quiz.router)
    # from handlers import stats
    # dp.include_router(stats.router)


def load_questions(topic, lang):
    fname = f"data/{topic}_{lang}.json"
    if not os.path.exists(fname):
        return []
    with open(fname, encoding="utf-8") as f:
        return json.load(f)

def filter_unsent_questions(questions, sent_ids):
    return [q for q in questions if q['id'] not in sent_ids]

async def send_topic_question(bot: Bot, topic: str):
    async with SessionLocal() as session:
        users_result = await session.execute(select(User))
        users = users_result.scalars().all()
        for user in users:
            lang = user.lang or 'ru'
            questions = load_questions(topic, lang)
            sent_result = await session.execute(
                select(QuestionSent.question_id).where(
                    QuestionSent.user_id == user.id,
                    QuestionSent.topic == topic
                )
            )
            sent_ids = [row[0] for row in sent_result.fetchall()]
            available = filter_unsent_questions(questions, sent_ids)
            if not available:
                continue
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
            kb = None
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            kb_builder = InlineKeyboardBuilder()
            for opt in q['options']:
                kb_builder.button(text=opt, callback_data=f"quiz_answer_{topic}_{opt}")
            kb_builder.adjust(2)
            kb = kb_builder.as_markup()
            try:
                if os.path.exists(img_path):
                    photo = InputFile(img_path)
                    await bot.send_photo(user.tg_id, photo, caption=text, reply_markup=kb)
                else:
                    await bot.send_message(user.tg_id, text, reply_markup=kb)
            except Exception as e:
                logging.warning(f"Не удалось отправить вопрос пользователю {user.tg_id}: {e}")

async def send_movie_question(bot: Bot):
    logging.info('Рассылка вопроса по фильму (12:00 МСК)')
    await send_topic_question(bot, 'movies')

async def send_city_question(bot: Bot):
    logging.info('Рассылка вопроса по городу (18:00 МСК)')
    await send_topic_question(bot, 'cities')

async def send_quiz_reminder(bot: Bot):
    async with SessionLocal() as session:
        users_result = await session.execute(select(User))
        users = users_result.scalars().all()
        for user in users:
            lang = user.lang or 'ru'
            locale = LOCALES.get(lang, LOCALES['ru'])
            try:
                await bot.send_message(
                    user.tg_id,
                    locale.get('reminder_msg', '🎯 Через 10 минут — новая викторина! Не пропусти!')
                )
            except Exception as e:
                logging.warning(f"Не удалось отправить напоминание пользователю {user.tg_id}: {e}")


def setup_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Europe/Moscow'))
    scheduler.add_job(send_movie_question, CronTrigger(hour=12, minute=0), args=[bot])
    scheduler.add_job(send_city_question, CronTrigger(hour=18, minute=0), args=[bot])
    # Новое: напоминания за 10 минут до вопросов
    scheduler.add_job(send_quiz_reminder, CronTrigger(hour=11, minute=50), args=[bot])
    scheduler.add_job(send_quiz_reminder, CronTrigger(hour=17, minute=50), args=[bot])
    scheduler.start()


async def main():
    global LOCALES
    LOCALES = get_locales()
    await init_db()

    from aiogram.client.default import DefaultBotProperties
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher()
    dp["locales"] = LOCALES  # 👈 ПЕРЕДАЕМ локали в диспетчер

    register_routers(dp)
    setup_scheduler(bot)
    logging.info('Bot started')
    await dp.start_polling(bot)



if __name__ == '__main__':
    asyncio.run(main())
