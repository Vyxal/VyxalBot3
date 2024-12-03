from enum import Enum
import inspect
from logging import getLogger
from typing import TYPE_CHECKING, Awaitable, Callable

from aiohttp import ClientSession
from sechat import Room
from sechat.events import BaseMessageEvent, MessageEvent

from vyxalbot3.commands.parser import ArgumentType, parse_arguments

if TYPE_CHECKING:
    from vyxalbot3.commands.parser import Argument


type CommandTree = dict[str, CommandTree] | Callable[..., Awaitable[str | None]]

ARGUMENT_TYPE_SIGNATURES = {
    int: ArgumentType.INT,
    float: ArgumentType.FLOAT,
    str: ArgumentType.STRING,
    list[str]: ArgumentType.STRARRAY,
}

PREFIX = "!!/"

class Commands:
    logger = getLogger("commands")

    def __init__(self, room: Room):
        self.room = room
        self.commands: dict[str, CommandTree] = {}

        for method_name, method in inspect.getmembers(self, inspect.ismethod):
            if method_name.startswith("__"):
                continue
            path = method_name.split("_")
            parent: dict[str, CommandTree] = self.commands
            while len(path) > 1:
                node = path.pop(0)
                if node not in parent:
                    parent[node] = {}
                new_parent = parent[node]
                if not isinstance(new_parent, dict):
                    raise Exception(f"A command group cannot itself be a command")
                parent = new_parent
            leaf = path[0]
            if leaf in parent:
                raise Exception(f"A command or group named {leaf} already exists in {parent}")
            parent[leaf] = method

    async def run(self):
        async with ClientSession(self.room._session._base_url) as session:
            async for event in self.room.events():
                match event:
                    case MessageEvent() if event.content.startswith(PREFIX) and len(event.content) > len(PREFIX):
                        async with session.get(f"/message/{event.message_id}?plain=true") as response:
                            content = (await response.text())
                        response = await self.handle_command(event, list(parse_arguments(content.removeprefix(PREFIX))))
                        if response is not None:
                            await self.room.send(response, event.message_id)


    async def handle_command(self, event: BaseMessageEvent, arguments: list["Argument"]):
        self.logger.debug(f"Handling command: {arguments}")
        command = self.commands
        match arguments[0]:
            case (ArgumentType.ERROR, message):
                return f"Parsing error: {message}"
            case (ArgumentType.FLAG, _):
                pass
            case _:
                return None
        for index, argument in enumerate(arguments):
            if argument[0] != ArgumentType.FLAG:
                break
            if argument[1] not in command:
                if index == 0:
                    return f"There is no command named \"{argument[1]}\"."
                parent_name = " ".join(a[1] for a in arguments[:index] if a[0] == ArgumentType.FLAG)
                return (
                    f"The command \"{parent_name}\" has no subcommand named \"{argument[1]}\". "
                    f"Its subcommands are: {", ".join(command.keys())}"
                )
            command = command[argument[1]]
            if not isinstance(command, dict):
                arguments = arguments[index + 1:]
                break
        if isinstance(command, dict):
            parent_name = " ".join(a[1] for a in arguments if a[0] == ArgumentType.FLAG)
            return f"Subcommands of \"{parent_name}\" are: {", ".join(command.keys())}"
        
        argument_values = []
        parameters = inspect.signature(command).parameters
        for argument_name, parameter in parameters.items():
            if argument_name in ("self", "event"):
                continue
            if issubclass(parameter.annotation, Enum):
                expected_type = ArgumentType.FLAG
            else:
                expected_type = ARGUMENT_TYPE_SIGNATURES[parameter.annotation]
            if len(arguments):
                match arguments.pop(0):
                    case (ArgumentType.ERROR, message):
                        return f"Parsing error: {message}"
                    case (ArgumentType.FLAG, name) if expected_type == ArgumentType.FLAG:
                        assert issubclass(parameter.annotation, Enum)
                        argument_values.append(parameter.annotation(name))
                    case (argument_type, value) if expected_type == argument_type:
                        argument_values.append(value)
                    case (actual_type, _):
                        return (
                            f"Incorrect type supplied for argument `{argument_name}`; "
                            f"expected **{expected_type.name}** but got **{actual_type.name}**"    
                        )
            elif parameter.default is not parameter.empty:
                argument_values.append(parameter.default)
            else:
                return f"Argument `{argument_name}` not provided, expected a value of type **{expected_type.name}**"
        if "event" in parameters:
            return await command(event, *argument_values)
        return await command(*argument_values)

    async def hello(self, name: str):
        return f"hello {name}"