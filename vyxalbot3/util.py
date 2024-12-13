import inspect
import re
from datetime import datetime
from typing import Any, Awaitable, Callable, Coroutine, overload

from aiohttp import ClientSession
from bs4 import BeautifulSoup, Tag
from sechat import Server
from yarl import URL


@overload
def autocache[**P, R](method: Callable[P, tuple[datetime, R]]) -> Callable[P, R]: ...


@overload
def autocache[
    **P, R
](method: Callable[P, Coroutine[Any, Any, tuple[datetime, R]]]) -> Callable[
    P, Coroutine[Any, Any, R]
]: ...


def autocache[
    **P, R
](
    method: Callable[P, tuple[datetime, R] | Coroutine[Any, Any, tuple[datetime, R]]]
) -> Callable[P, R | Coroutine[Any, Any, R]]:
    value: tuple[datetime, R] | None = None

    async def _store(ret: Awaitable[tuple[datetime, R]]) -> R:
        value = await ret
        return value[1]

    def _wrapper(*args: P.args, **kwargs: P.kwargs):
        nonlocal value
        if value is None or value[0] < datetime.now():
            ret = method(*args, **kwargs)
            if inspect.isawaitable(ret):
                return _store(ret)
            value = ret
        return value[1]

    return _wrapper


MESSAGE_LINK_REGEX = (
    r"https?://chat.stackexchange.com/transcript(/message)?/(?P<id>\d+)(#.*)?"
)


def extract_message_id(raw: str) -> int | None:
    if raw.isdigit():
        return int(raw)
    elif (match := re.fullmatch(MESSAGE_LINK_REGEX, raw)) is not None:
        return int(match.groupdict()["id"])
    else:
        return None


async def get_message_room(
    session: ClientSession, server: Server, message: int
) -> int | None:
    async with session.get(f"{server}/transcript/message/{message}") as response:
        if response.status != 200:
            return None
        soup = BeautifulSoup(await response.read())
        assert isinstance(room_name := soup.find(class_="room-name"), Tag)
        assert isinstance(link := room_name.find("a"), Tag)
        assert isinstance(href := link["href"], str)
        return int(URL(href).parts[2])


async def get_messages_between(
    session: ClientSession, server: Server, fkey: str, room: int, start: int, end: int
):
    before = end
    yield end
    while True:
        async with session.post(
            f"{server}/chats/{room}/events",
            data={"before": str(before), "mode": "Messages", "msgCount": 500},
        ) as response:
            data = await response.json()
            events = data["events"]
            ids: list[int] = [event["message_id"] for event in events]
            if start in ids:
                for ident in reversed(ids[ids.index(start) :]):
                    yield ident
                break
            for ident in reversed(ids):
                yield ident
            before = ids[0]
