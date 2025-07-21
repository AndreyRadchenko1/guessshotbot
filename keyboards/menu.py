from aiogram.utils.keyboard import InlineKeyboardBuilder
from main import LOCALES


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
