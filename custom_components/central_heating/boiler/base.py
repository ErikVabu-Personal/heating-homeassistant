"""Controller-independent command boundary."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BoilerCommand:
    heat: bool
    room_temperature: float | None
    setpoint: float


class BoilerAdapter(Protocol):
    last_success: bool

    async def async_start(self) -> None: ...
    async def async_apply(self, cmd: BoilerCommand, *, keepalive: bool) -> None: ...
    async def async_stop(self, *, unloading: bool) -> None: ...
