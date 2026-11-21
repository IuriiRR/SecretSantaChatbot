from aiogram.fsm.state import State, StatesGroup


class SecretSantaStates(StatesGroup):
    """Finite state machine states for Secret Santa bot interactions."""

    join_group = State()
    add_player = State()
    add_pair = State()
