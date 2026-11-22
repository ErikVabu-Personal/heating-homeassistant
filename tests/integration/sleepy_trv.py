"""A battery TRV queues radio writes and applies them in order when it wakes."""

from collections import deque

from homeassistant.core import Context


class SleepyTRV:
    """Install a local climate service: one sleepy TRV, other TRVs respond immediately.

    Optimistic HA reports carry the command's Context but do not change physical state.
    Device reports use a fresh Context. A wake can lose the queued writes to model a radio
    failure; a stale report then reflects the unchanged physical device.
    """

    def __init__(self, hass, entity_id: str, *, optimistic: bool = False):
        self.hass = hass
        self.entity_id = entity_id
        self.optimistic = optimistic
        state = hass.states.get(entity_id)
        self.physical_target = state.attributes["temperature"]
        self.physical_mode = state.state
        self.queue = deque()
        self.sent = []
        hass.services.async_register("climate", "set_temperature", self.handle)

    def report(self, target, *, context=None, mode=None):
        state = self.hass.states.get(self.entity_id)
        self.hass.states.async_set(
            self.entity_id,
            self.physical_mode if mode is None else mode,
            {**state.attributes, "temperature": target},
            context=context or Context(),
        )

    async def handle(self, call):
        if call.data["entity_id"] != self.entity_id:
            state = self.hass.states.get(call.data["entity_id"])
            self.hass.states.async_set(
                call.data["entity_id"],
                call.data.get("hvac_mode", state.state),
                {**state.attributes, "temperature": call.data["temperature"]},
                context=Context(),
            )
            return
        self.queue.append(call)
        self.sent.append(call)
        if self.optimistic:
            self.report(
                call.data["temperature"],
                context=call.context,
                mode=call.data.get("hvac_mode", self.physical_mode),
            )

    async def stale(self):
        self.report(self.physical_target)
        await self.hass.async_block_till_done()

    async def wake(self, *, lose_commands=False, count=None):
        """Apply queued commands sequentially, including their intermediate reports."""
        remaining = len(self.queue) if count is None else min(count, len(self.queue))
        for _ in range(remaining):
            call = self.queue.popleft()
            if not lose_commands:
                self.physical_target = call.data["temperature"]
                self.physical_mode = call.data.get("hvac_mode", self.physical_mode)
                self.report(self.physical_target)
                await self.hass.async_block_till_done()
