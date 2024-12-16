from asyncio import TaskGroup
from logging import getLogger

from aiohttp import ClientSession
from aiohttp.web import Application, AppRunner, Response, TCPSite, get, post
from sechat import Credentials, Room

from prisma import Prisma
from vyxalbot3.commands import Commands
from vyxalbot3.commands.dispatcher import CommandDispatcher
from vyxalbot3.github import AppGitHubAPI
from vyxalbot3.github.webhook import GitHubWebhookReporter
from vyxalbot3.settings import Settings, SupplementaryConfiguration


async def _index(_):
    return Response(body=":3")


async def main(settings: Settings, config: SupplementaryConfiguration):
    logger = getLogger("main")
    app = Application(logger=logger.getChild("web"))
    runner = AppRunner(app)
    db = Prisma()

    credentials = await Credentials.load_or_authenticate(
        "credentials.dat",
        settings.chat.email,
        settings.chat.password,
        server=settings.chat.server,
    )
    async with await Room.join(
        credentials, settings.chat.room
    ) as room, ClientSession() as session:
        gh = AppGitHubAPI(
            session,
            settings.github.account,
            str(settings.github.app_id),
            settings.github.private_key,
        )
        commands = Commands(room, db, gh, config)
        dispatcher = CommandDispatcher(room, db, commands.tree, config.reactions)
        webhook = GitHubWebhookReporter(room, db, gh, settings.webhook.secret, set())
        app.add_routes(
            [
                get("/", _index),
                post("/webhook", webhook.handle_request),
            ]
        )
        await runner.setup()
        site = TCPSite(runner, host=settings.webhook.host, port=settings.webhook.port)
        await site.start()
        await db.connect()
        try:
            async with TaskGroup() as group:
                group.create_task(dispatcher.run())
                logger.info("Startup complete")
        finally:
            logger.info("Shutting down")
            await db.disconnect()
            await runner.cleanup()
