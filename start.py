from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import SessionLocal, get_or_create_user
from states import LangState
from aiogram.fsm.context import FSMContext

from main import LOCALES

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="lang_ru")
    kb.button(text="🇬🇧 English", callback_data="lang_en")
    kb.adjust(2)

    await state.set_state(LangState.waiting_for_lang)
    await message.answer("Choose your language / Выберите язык:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("lang_"))
async def lang_chosen(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]

    async with SessionLocal() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        user.lang = lang
        await session.commit()

    locale = LOCALES.get(lang, LOCALES.get("ru", {}))  # защищаем от KeyError

    kb = InlineKeyboardBuilder()
    kb.button(text=locale.get("play_btn", "🎮 Играть"), callback_data="menu_play")
    kb.button(text=locale.get("stats_btn", "📊 Моя статистика"), callback_data="menu_stats")
    kb.button(text=locale.get("rating_btn", "🏆 Рейтинг дня"), callback_data="menu_rating")
    kb.adjust(1)

    await callback.message.answer(locale.get("menu", "Выберите действие:"), reply_markup=kb.as_markup())
    await callback.answer()
    await state.clear()

