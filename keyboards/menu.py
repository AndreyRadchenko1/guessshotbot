from aiogram.utils.keyboard import InlineKeyboardBuilder
from main import LOCALES
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_menu_keyboard(lang: str):
    locale = LOCALES.get(lang, LOCALES['ru'])
    kb = InlineKeyboardBuilder()
    kb.button(
        text=locale.get('play_btn', '🎬 Играть'),
        callback_data='menu_play',
    )
    kb.button(
        text=locale.get('stats_btn', '📊 Моя статистика'),
        callback_data='menu_stats',
    )
    kb.button(
        text=locale.get('rating_btn', '🏆 Ежедневный рейтинг'),
        callback_data='menu_rating',
    )
    kb.adjust(1)
    return kb.as_markup()


def get_reply_menu_keyboard(lang: str):
    locale = LOCALES.get(lang, LOCALES['ru'])
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=locale.get('play_btn', '🎬 Играть')
                ),
            ],
            [
                KeyboardButton(
                    text=locale.get('stats_btn', '📊 Моя статистика')
                ),
            ],
            [
                KeyboardButton(
                    text=locale.get('rating_btn', '🏆 Ежедневный рейтинг')
                ),
            ],
            [
                KeyboardButton(
                    text=locale.get('achievements_btn', '🏅 Ачивки-лидеры')
                ),
            ],
            [
                KeyboardButton(
                    text=locale.get('profile_btn', '👤 Профиль')
                ),
            ],
            [
                KeyboardButton(
                    text=locale.get('feedback_btn', '💬 Отзывы и предложения')
                ),
            ],
        ],
        resize_keyboard=True
    )
