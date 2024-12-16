import inspect
from enum import Enum, EnumType
from itertools import zip_longest
from types import NoneType, UnionType
from typing import Any, Mapping

from aiohttp import ClientSession
from prisma.models import User
from sechat import Room
from sechat.events import MessageEvent

from prisma import Prisma
from vyxalbot3.commands import (
    ADMIN_GROUP,
    ARGUMENT_TYPE_SIGNATURES,
    COMMAND_FUNCTION_SUFFIX,
    IGNORED_PARAMETERS,
    PREFIX,
    CommandLeaf,
    CommandTree,
)
from vyxalbot3.commands.parser import (
    Argument,
    ArgumentType,
    ParseError,
    parse_arguments,
)


class CommandDispatcher:
    def __init__(self, room: Room, db: Prisma, tree: dict[str, CommandTree]):
        self.tree = tree
        self.room = room
        self.db = db

    async def run(self):
        async with ClientSession(self.room._session._base_url) as session:
            async for event in self.room.events():
                match event:
                    case MessageEvent() if PREFIX in event.content:
                        async with session.get(
                            f"/message/{event.message_id}?plain=true"
                        ) as response:
                            content = await response.text()
                        if not (
                            content.startswith(PREFIX) and len(content) > len(PREFIX)
                        ):
                            continue
                        current_user = await self.db.user.upsert(
                            where={"id": event.user_id},
                            data={
                                "create": {
                                    "id": event.user_id,
                                    "name": event.user_name,
                                    "groups": {},
                                },
                                "update": {"name": event.user_name},
                            },
                            include={"groups": True},
                        )
                        try:
                            arguments = parse_arguments(content.removeprefix(PREFIX))
                        except ParseError as error:
                            await self.room.send(
                                f"Parse error: {error.message}", event.message_id
                            )
                        else:
                            match (
                                await self.handle(
                                    event,
                                    current_user,
                                    *arguments,
                                )
                            ):
                                case str(message):
                                    await self.room.send(message, event.message_id)
                                case (message, reply_to):
                                    await self.room.send(message, reply_to)

    def split_arguments(
        self, arguments: list[Argument]
    ) -> tuple[CommandLeaf, list[Argument]] | tuple[dict[str, CommandTree], str | None]:
        command: CommandTree = self.tree
        for index, argument in enumerate(arguments):
            if argument[0] != ArgumentType.FLAG:
                break
            if argument[1] not in command:
                return command, argument[1]
            command = command[argument[1]]
            if not isinstance(command, dict):
                return command, arguments[index + 1 :]
        return command, None

    def find_expected_types(self, parameters: Mapping[str, inspect.Parameter]):
        expected_types: dict[str, ArgumentType] = {}
        for parameter in parameters.values():
            if parameter.name in IGNORED_PARAMETERS:
                continue
            if isinstance(parameter.annotation, EnumType):
                expected_type = ArgumentType.FLAG
            elif isinstance(parameter.annotation, UnionType):
                assert parameter.annotation.__args__[1] == NoneType
                assert parameter.default == None
                expected_type = ARGUMENT_TYPE_SIGNATURES[
                    parameter.annotation.__args__[0]
                ]
            else:
                expected_type = ARGUMENT_TYPE_SIGNATURES[parameter.annotation]
            expected_types[parameter.name] = expected_type
        return expected_types

    def prepare_arguments(
        self,
        command: CommandLeaf,
        arguments: list[Argument],
        explicit_arguments: dict[str, Argument],
        context: dict[str, Any] = {},
    ) -> dict[str, Any] | str:
        argument_values = {}
        parameters = inspect.signature(command).parameters
        expected_types = self.find_expected_types(parameters)

        def _set_argument(parameter: inspect.Parameter, argument: Argument):
            expected_type = expected_types[parameter.name]
            match argument:
                case (
                    ArgumentType.FLAG,
                    name,
                ) if expected_type == ArgumentType.FLAG:
                    assert isinstance(parameter.annotation, EnumType)
                    try:
                        argument_values[parameter.name] = parameter.annotation(name)
                    except ValueError:
                        values = "/".join(
                            item.value
                            for item in list(parameter.annotation)
                            if isinstance(item, Enum)
                        )
                        return (
                            f"Invalid value supplied for argument `{parameter.name}`; "
                            f"expected one of {values}."
                        )
                case (argument_type, value) if expected_type == argument_type:
                    argument_values[parameter.name] = value
                case (actual_type, _):
                    return (
                        f"Incorrect type supplied for argument `{parameter.name}`; "
                        f"expected **{expected_type.name}** but got **{actual_type.name}**"
                    )

        # Set positional arguments
        for parameter, argument in zip_longest(
            parameters.values(), arguments, fillvalue=None
        ):
            if argument is None:
                break
            if parameter is None:
                return f"Superfluous arguments supplied starting at `{argument[1]}`."
            if parameter.name in IGNORED_PARAMETERS:
                continue
            if (error := _set_argument(parameter, argument)) is not None:
                return error

        # Set keyword arguments
        for argument_name, argument in explicit_arguments.items():
            if argument_name in IGNORED_PARAMETERS:
                return f"Illegal argument `{argument_name}` supplied."
            if argument_name in argument_values:
                return f"Multiple values supplied for argument `{argument_name}`."
            if (parameter := parameters.get(argument_name)) is None:
                return f"Unknown argument `{argument_name}` supplied."
            if (error := _set_argument(parameter, argument)) is not None:
                return error

        # Find missing arguments
        for parameter in parameters.values():
            if parameter.name in IGNORED_PARAMETERS:
                continue
            if (
                parameter.name not in argument_values
                and parameter.default is parameter.empty
            ):
                expected_type = expected_types[parameter.name]
                return f"Argument `{parameter.name}` not provided, expected a value of type **{expected_type.name}**."

        # Set context values
        for key, value in context.items():
            if key in parameters:
                argument_values[key] = value

        return argument_values

    async def handle(
        self,
        event: MessageEvent,
        current_user: User,
        full_arguments: list[Argument],
        explicit_arguments: dict[str, Argument],
    ):
        if full_arguments[0][0] != ArgumentType.FLAG:
            return None
        match self.split_arguments(full_arguments):
            case (tree, str(nonexistent_leaf)):
                # The command referred to a group member or toplevel command that doesn't exist
                if (
                    trick := await self.db.trick.find_unique(
                        where={"name": nonexistent_leaf}
                    )
                ) is not None:
                    return trick.body
                if tree == self.tree:
                    return f"There is no command named !!/{nonexistent_leaf}."
                parent_name = " ".join(str(a[1]) for a in full_arguments[:-1])
                return (
                    f'The group !!/{parent_name} has no subcommand named "{nonexistent_leaf}". '
                    f"Its subcommands are: {", ".join(tree.keys())}"
                )
            case (tree, None):
                # The command ended on a group name
                group_name = " ".join(str(a[1]) for a in full_arguments)
                return f"Subcommands of !!/{group_name} are: {", ".join(tree.keys())}"
            case (command, arguments):
                assert current_user.groups is not None
                permissions = await self.db.commandpermission.find_many(
                    where={
                        "command": command.__name__.removesuffix(
                            COMMAND_FUNCTION_SUFFIX
                        ).replace("_", " ")
                    }
                )
                user_groups = set(group.group_name for group in current_user.groups)
                allowed_groups = set(
                    permission.group_name for permission in permissions
                )
                if (
                    ADMIN_GROUP not in user_groups
                    and len(allowed_groups)
                    and not len(user_groups & allowed_groups)
                ):
                    return f"Only members of groups {" | ".join(f"_{name}_" for name in allowed_groups)} may run that command."

                match self.prepare_arguments(
                    command,
                    arguments,
                    explicit_arguments,
                    {
                        "event": event,
                        "current_user": current_user,
                    },
                ):
                    case str(error):
                        return error
                    case argument_values:
                        return await command(**argument_values)
