"""Fallback authorization independent of provider runners."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from .failures import FALLBACK_ELIGIBLE, FailureClass
from .frontmatter import ModelFallbackMode
from .resolver import ResolvedModel


class FallbackAction(StrEnum):
    RETRY = "retry"
    STOP = "stop"
    NEEDS_CONFIRMATION = "needs_confirmation"


@dataclass(frozen=True)
class FallbackDecision:
    action: FallbackAction
    current: ResolvedModel
    proposed: ResolvedModel | None
    failure: FailureClass
    message: str
    confirmed: bool = False


class FallbackController:
    def __init__(
        self,
        chain: Sequence[ResolvedModel],
        mode: ModelFallbackMode,
        *,
        interactive: bool = False,
        confirm_callback: Callable[[str], bool] | None = None,
    ) -> None:
        if not chain or len(chain) > 4:
            raise ValueError("fallback chain must contain 1 to 4 attempts")
        self.chain = tuple(chain)
        self.mode = ModelFallbackMode(mode)
        self.interactive = interactive
        self.confirm_callback = confirm_callback

    def decide(self, index: int, failure: FailureClass) -> FallbackDecision:
        current = self.chain[index]
        proposed = self.chain[index + 1] if index + 1 < len(self.chain) else None
        message = f"{failure.value}: {current.tier}"
        if failure not in FALLBACK_ELIGIBLE or proposed is None:
            return FallbackDecision(
                FallbackAction.STOP, current, proposed, failure, message
            )
        message = f"{failure.value}: switch {current.tier} to {proposed.tier}"
        if self.mode is ModelFallbackMode.AUTO:
            return FallbackDecision(
                FallbackAction.RETRY, current, proposed, failure, message, True
            )
        if not self.interactive or self.confirm_callback is None:
            return FallbackDecision(
                FallbackAction.NEEDS_CONFIRMATION, current, proposed, failure, message
            )
        confirmed = bool(self.confirm_callback(message))
        return FallbackDecision(
            FallbackAction.RETRY if confirmed else FallbackAction.STOP,
            current,
            proposed,
            failure,
            message,
            confirmed,
        )
