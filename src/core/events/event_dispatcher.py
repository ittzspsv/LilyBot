import asyncio
import functools
import inspect
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Optional, Set

from discord import Guild
from enum import Enum
from discord.ext.commands import Bot

log = logging.getLogger("lily")


@dataclass(frozen=True)
class EventPayload:
    bot: Bot
    guild: Guild

class Events(str, Enum):
    LEVEL_UP = "on_level_up"


class EventDispatcher:
    def __init__(self) -> None:
        self._events: Set[str] = set()
        self._handlers = defaultdict(list)

    def preload_events(self, events: Set[str]) -> None:
        self._events.update(events)

    def register(self, event_name: str, handler: Callable) -> None:
        if event_name not in self._events:
            raise ValueError(f"Invalid event: {event_name}")

        if handler in self._handlers[event_name]:
            return

        self._handlers[event_name].append(handler)

    @staticmethod
    def _validate_handler(fn: Callable) -> None:
        params = list(inspect.signature(fn).parameters.values())
        positional = (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        if not params or params[0].kind not in positional:
            raise TypeError(
                f"{fn.__qualname__} must take the event payload as its "
                f"first positional parameter, e.g. "
                f"`async def {fn.__name__}(payload: EventPayload, **kwargs)`"
            )

    def event(self, func: Optional[Callable] = None, *, name: Optional[str] = None):
        def decorator(fn: Callable) -> Callable:
            self._validate_handler(fn)
            event_name = name or fn.__name__
            self.register(event_name, fn)
            log.info("Registered event handler %s for event %r", fn.__qualname__, event_name)
            return fn

        if func is not None:     
            return decorator(func)
        return decorator          

    async def _event_executor(self, func, *args, **kwargs):
        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)

    async def invoke(self, name: str, payload: EventPayload, **kwargs) -> None:
        if name not in self._events:
            raise ValueError(f"Unknown event: {name}")

        handlers = list(self._handlers.get(name, []))
        results = await asyncio.gather(
            *(self._event_executor(h, payload, **kwargs) for h in handlers),
            return_exceptions=True,
        )
        for handler, result in zip(handlers, results):
            if isinstance(result, BaseException):
                log.error(
                    "Handler %s failed for event %r",
                    handler.__qualname__, name, exc_info=result,
                )


dispatcher = EventDispatcher()
dispatcher.preload_events({event.value for event in Events})
event = dispatcher.event