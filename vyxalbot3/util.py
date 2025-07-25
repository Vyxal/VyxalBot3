import re

from aiohttp import ClientSession
from bs4 import BeautifulSoup, Tag
from sechat import Server
from yarl import URL

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
        soup = BeautifulSoup(await response.read(), features="lxml")
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
            data={
                "before": str(before),
                "mode": "Messages",
                "msgCount": 500,
                "fkey": fkey,
            },
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
