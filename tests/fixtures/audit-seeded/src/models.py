"""Typed models for the demo dashboard."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    game_id: int
    user_id: int
    value: float

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(f"score value must be >= 0, got {self.value}")
