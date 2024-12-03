from collections.abc import Callable
from functools import wraps
from logging import getLogger
from pprint import pformat
from typing import AsyncGenerator, Awaitable
from aiohttp.web import Request, Response
from gidgethub import BadRequest, ValidationError
from gidgethub.sansio import Event
from gidgethub.routing import Router
from sechat import Room

class GitHubWebhookReporter:
    logger = getLogger("GitHubWebhook")
    router = Router()

    @staticmethod
    def handler(func: Callable[[Event, Room], AsyncGenerator[str | tuple[str, int], int]]) -> Callable[[Event, "GitHubWebhookReporter"], Awaitable[None]]:
        @wraps(func)
        async def _wrapper(event: Event, self: "GitHubWebhookReporter"):
            generator = func(event, self.room)
            message = await anext(generator)
            while True:
                try:
                    if isinstance(message, str):
                        message_id = await self.room.send(message)
                    else:
                        message_id = await self.room.send(*message)
                    message = await generator.asend(message_id)
                except StopAsyncIteration:
                    break
        return _wrapper


    def __init__(self, room: Room, webhook_secret: str, ignored_repositories: set[str]):
        self.room = room
        self.webhook_secret = webhook_secret
        self.ignored_repositories = ignored_repositories
        
    async def handle_request(self, request: Request) -> Response:
        try:
            event = Event.from_http(request.headers, await request.read(), secret=self.webhook_secret)
        except (BadRequest, ValidationError):
            return Response(status=400)
        assert isinstance(event.data, dict)
        if repository := event.data.get("repository", False):
            if repository["visibility"] == "private" or repository["name"] in self.ignored_repositories:
                return Response(status=200)
        try:
            await self.router.dispatch(event)
        except Exception:
            self.logger.exception(f"Failed to handle event {event.delivery_id} with payload:\n{pformat(event.data)}")
            return Response(status=500)
        return Response(status=200)

    @handler
    @staticmethod
    async def on_push(event: Event, room: Room):
        yield "pushed"