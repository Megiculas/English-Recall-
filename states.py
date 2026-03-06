from aiogram.fsm.state import State, StatesGroup

class EditTranslationState(StatesGroup):
    waiting_for_translation = State()
