import inspect
import random
from enum import Enum, EnumType
from logging import getLogger
import re
from types import NoneType, UnionType
from typing import TYPE_CHECKING, Awaitable, Callable

from aiohttp import ClientSession
from sechat import Room
from sechat.events import MessageEvent, MessageEvent
from uwuipy import Uwuipy

from vyxalbot3.commands.messages import *
from vyxalbot3.commands.parser import ArgumentType, parse_arguments

if TYPE_CHECKING:
    from vyxalbot3.commands.parser import Argument


type CommandTree = dict[str, CommandTree] | Callable[..., Awaitable[str | tuple[str, int | None] | None]]

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
            if not method_name.endswith("_command"):
                continue
            path = method_name.removesuffix("_command").split("_")
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
                        match (await self.handle(event, list(parse_arguments(content.removeprefix(PREFIX))))):
                            case str(message):
                                await self.room.send(message, event.message_id)
                            case (message, reply_to):
                                await self.room.send(message, reply_to)


    async def handle(self, event: MessageEvent, arguments: list["Argument"]):
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
                    return f"There is no command named !!/{argument[1]}."
                parent_name = " ".join(a[1] for a in arguments[:index] if a[0] == ArgumentType.FLAG)
                return (
                    f"The group !!/{parent_name} has no subcommand named \"{argument[1]}\". "
                    f"Its subcommands are: {", ".join(command.keys())}"
                )
            command = command[argument[1]]
            if not isinstance(command, dict):
                arguments = arguments[index + 1:]
                break
        if isinstance(command, dict):
            parent_name = " ".join(a[1] for a in arguments if a[0] == ArgumentType.FLAG)
            return f"Subcommands of !!/{parent_name} are: {", ".join(command.keys())}"
        
        argument_values = []
        parameters = inspect.signature(command).parameters
        for name, parameter in parameters.items():
            if name in ("self", "event"):
                continue
            if isinstance(parameter.annotation, EnumType):
                expected_type = ArgumentType.FLAG
            elif isinstance(parameter.annotation, UnionType):
                assert parameter.annotation.__args__[1] == NoneType
                assert parameter.default == None
                expected_type = ARGUMENT_TYPE_SIGNATURES[parameter.annotation.__args__[0]]
            else:
                expected_type = ARGUMENT_TYPE_SIGNATURES[parameter.annotation]
            if len(arguments):
                match arguments.pop(0):
                    case (ArgumentType.ERROR, message):
                        return f"Parsing error: {message}"
                    case (ArgumentType.FLAG, name) if expected_type == ArgumentType.FLAG:
                        assert isinstance(parameter.annotation, EnumType)
                        argument_values.append(parameter.annotation(name))
                    case (argument_type, value) if expected_type == argument_type:
                        argument_values.append(value)
                    case (actual_type, _):
                        return (
                            f"Incorrect type supplied for argument `{name}`; "
                            f"expected **{expected_type.name}** but got **{actual_type.name}**"    
                        )
            elif parameter.default is not parameter.empty:
                argument_values.append(parameter.default)
            else:
                return f"Argument `{name}` not provided, expected a value of type **{expected_type.name}**"
        if "event" in parameters:
            return await command(event, *argument_values)
        return await command(*argument_values)

    async def help_command(self, name: str):
        """Display parameters and help for a command."""
        if name == "me":
            return "I'd love to, but I don't have any limbs."
        path = name.split(" ")
        help_target = self.commands
        for index, segment in enumerate(path):
            if segment not in help_target:
                if index == 0:
                    return f"There is no command named \"{segment}\"."
                parent_name = " ".join(path[:index])
                return (
                    f"The group \"{parent_name}\" has no subcommand named \"{segment}\". "
                    f"Its subcommands are: {", ".join(help_target.keys())}"
                )
            help_target = help_target[segment]
            if not isinstance(help_target, dict):
                break
        if isinstance(help_target, dict):
            parent_name = " ".join(path)
            return f"Subcommands of !!/{parent_name} are: {", ".join(help_target.keys())}"
        
        doc = help_target.__doc__ if help_target.__doc__ is not None else "(no help)"
        parameters = []
        for parameter_name, parameter in inspect.signature(help_target).parameters.items():
            if name in ("self", "event"):
                continue
            if isinstance(parameter.annotation, EnumType):
                values = "/".join(item.value for item in list(parameter.annotation) if isinstance(item, Enum))
                body = f"ENUM {parameter_name}: {values}"
            elif isinstance(parameter.annotation, UnionType):
                body = f"{ARGUMENT_TYPE_SIGNATURES[parameter.annotation.__args__[0]].name} {parameter_name}"
            else:
                body = f"{ARGUMENT_TYPE_SIGNATURES[parameter.annotation].name} {parameter_name}"
            if parameter.default != parameter.empty:
                if parameter.default == None:
                    parameters.append(f"[{body}]")
                else:
                    default = parameter.default.value if isinstance(parameter.default, Enum) else repr(parameter.default)
                    parameters.append(f"[{body} = {default}]")
            else:
                parameters.append(f"({body})")
        return f"`!!/{name} {" ".join(parameters)}`: {doc}"

    async def commands_command(self):
        return f"All commands: {", ".join(self.commands.keys())}"

    # Fun commands -----------------

    class StatusMood(Enum):
        NORMAL = "normal"
        TINGLY = "tingly"
    async def status_command(self, mood: StatusMood = StatusMood.NORMAL):
        status = random.choice(STATUSES)
        match mood:
            case Commands.StatusMood.NORMAL:
                return status
            case Commands.StatusMood.TINGLY:
                return Uwuipy().uwuify(status)
            
    async def coffee_command(self, target: str | None = None):
        if target is None:
            return "☕"
        else:
            return f"@{target} ☕"
            
    async def maul_command(self, event: MessageEvent, target: str):
        if re.fullmatch(r"me|(vyxal ?bot\d*)", target, re.IGNORECASE) is not None:
            return RAPTOR.format(user=event.user_name.capitalize()), None
        else:
            return RAPTOR.format(user=target.capitalize()), None
        
    async def hug_command(self, target: str | None = None):
        if target is None:
            return random.choice(HUGS)
        else:
            return f"*gives @{target} a hug.* {random.choice(HUGS)}"

    async def sus_command(self):
        return "ඞ" * random.randint(8, 64)

    async def amilyxal_command(self, event: MessageEvent):
        return f"You are {"" if (event.user_id == 354515) != (random.random() <= 0.1) else "not "}lyxal."

    async def cookie_command(self):
        # TODO: Check for adminship
        if random.random() <= 0.75:
            return "Here you go: 🍪"
        else:
            return "No."