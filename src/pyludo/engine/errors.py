class LudoError(Exception):
    """Base for all errors"""

    code: str = "ludo_error"
    message: str = "error"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)


class InvalidPlayerCountError(LudoError):
    code = "invalid_player_count"
    message = "player count must be between 2 and 4"


class GameOverError(LudoError):
    code = "game_over"
    message = "game is over"


class NotAwaitingRollError(LudoError):
    code = "not_awaiting_roll"
    message = "not awaiting a roll"


class NotAwaitingMoveError(LudoError):
    code = "not_awaiting_move"
    message = "not awaiting a move"


class DieOutOfRangeError(LudoError):
    code = "die_out_of_range"
    message = "die must be between 1 and 6"


class InvalidTokenIndexError(LudoError):
    code = "invalid_token_index"
    message = "token index must be between 0 and 3"


class IllegalMoveError(LudoError):
    code = "illegal_move"
    message = "move is not legal for the pending die"
