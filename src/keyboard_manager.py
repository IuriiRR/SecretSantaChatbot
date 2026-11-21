from aiogram.types import InlineKeyboardMarkup


class KeyboardManager:
    """Helper factory for inline keyboards."""

    @staticmethod
    def get_inline_keyboard() -> InlineKeyboardMarkup:
        """Return an empty inline keyboard markup."""
        return InlineKeyboardMarkup(inline_keyboard=[])
