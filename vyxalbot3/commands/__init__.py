import inspect
import random
import re
from enum import Enum, EnumType
from logging import getLogger
from types import NoneType, UnionType
from typing import TYPE_CHECKING, Awaitable, Callable, cast

from aiohttp import ClientSession
from prisma import Prisma
from prisma.models import User, Group
from prisma.errors import RecordNotFoundError
from sechat import Room
from sechat.events import MessageEvent
from uwuipy import Uwuipy

from vyxalbot3.commands.messages import *
from vyxalbot3.commands.parser import ArgumentType, parse_arguments

if TYPE_CHECKING:
    from vyxalbot3.commands.parser import Argument

type CommandTree = dict[str, CommandTree] | Callable[
    ..., Awaitable[str | tuple[str, int | None] | None]
]

ARGUMENT_TYPE_SIGNATURES = {
    int: ArgumentType.INT,
    float: ArgumentType.FLOAT,
    str: ArgumentType.STRING,
    list[str]: ArgumentType.STRARRAY,
}
IGNORED_PARAMETERS = ("self", "event", "current_user")
COMMAND_FUNCTION_SUFFIX = "_command"

PREFIX = "!!/"

ADMIN_GROUP = "admin"


class Commands:
    logger = getLogger("commands")

    def __init__(self, room: Room, db: Prisma):
        self.room = room
        self.db = db
        self.commands: dict[str, CommandTree] = {}

        for method_name, method in inspect.getmembers(self, inspect.ismethod):
            if not method_name.endswith(COMMAND_FUNCTION_SUFFIX):
                continue
            path = method_name.removesuffix(COMMAND_FUNCTION_SUFFIX).split("_")
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
                raise Exception(
                    f"A command or group named {leaf} already exists in {parent}"
                )
            parent[leaf] = method

    async def run(self):
        async with ClientSession(self.room._session._base_url) as session:
            async for event in self.room.events():
                match event:
                    case MessageEvent() if event.content.startswith(PREFIX) and len(
                        event.content
                    ) > len(PREFIX):
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
                        async with session.get(
                            f"/message/{event.message_id}?plain=true"
                        ) as response:
                            content = await response.text()
                        match (
                            await self.handle(
                                event,
                                current_user,
                                list(parse_arguments(content.removeprefix(PREFIX))),
                            )
                        ):
                            case str(message):
                                await self.room.send(message, event.message_id)
                            case (message, reply_to):
                                await self.room.send(message, reply_to)

    async def handle(
        self, event: MessageEvent, current_user: User, arguments: list["Argument"]
    ):
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
                parent_name = " ".join(
                    a[1] for a in arguments[:index] if a[0] == ArgumentType.FLAG
                )
                return (
                    f'The group !!/{parent_name} has no subcommand named "{argument[1]}". '
                    f"Its subcommands are: {", ".join(command.keys())}"
                )
            command = command[argument[1]]
            if not isinstance(command, dict):
                arguments = arguments[index + 1 :]
                break
        if isinstance(command, dict):
            parent_name = " ".join(a[1] for a in arguments if a[0] == ArgumentType.FLAG)
            return f"Subcommands of !!/{parent_name} are: {", ".join(command.keys())}"

        assert current_user.groups is not None
        permissions = await self.db.commandpermission.find_many(
            where={
                "command": command.__name__.removesuffix(
                    COMMAND_FUNCTION_SUFFIX
                ).replace("_", " ")
            }
        )
        allowed_groups = set(permission.group_name for permission in permissions)
        if len(allowed_groups) and not len(
            set(group.group_name for group in current_user.groups) & allowed_groups
        ):
            return f"Only members of groups {" | ".join(f"_{name}_" for name in allowed_groups)} may run that command."

        argument_values = []
        parameters = inspect.signature(command).parameters
        for parameter_name, parameter in parameters.items():
            if parameter_name in IGNORED_PARAMETERS:
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
            if len(arguments):
                match arguments.pop(0):
                    case (ArgumentType.ERROR, message):
                        return f"Parsing error: {message}"
                    case (
                        ArgumentType.FLAG,
                        name,
                    ) if expected_type == ArgumentType.FLAG:
                        assert isinstance(parameter.annotation, EnumType)
                        argument_values.append(parameter.annotation(name))
                    case (argument_type, value) if expected_type == argument_type:
                        argument_values.append(value)
                    case (actual_type, _):
                        return (
                            f"Incorrect type supplied for argument `{parameter_name}`; "
                            f"expected **{expected_type.name}** but got **{actual_type.name}**"
                        )
            elif parameter.default is not parameter.empty:
                argument_values.append(parameter.default)
            else:
                return f"Argument `{parameter_name}` not provided, expected a value of type **{expected_type.name}**"
        keyword_args = {}
        if "event" in parameters:
            keyword_args["event"] = event
        if "current_user" in parameters:
            keyword_args["current_user"] = current_user
        return await command(*argument_values, **keyword_args)

    async def help_command(self, name: str):
        """Display parameters and help for a command."""
        if name == "me":
            return "I'd love to, but I don't have any limbs."
        path = name.split(" ")
        help_target = self.commands
        for index, segment in enumerate(path):
            if segment not in help_target:
                if index == 0:
                    return f'There is no command named "{segment}".'
                parent_name = " ".join(path[:index])
                return (
                    f'The group "{parent_name}" has no subcommand named "{segment}". '
                    f"Its subcommands are: {", ".join(help_target.keys())}"
                )
            help_target = help_target[segment]
            if not isinstance(help_target, dict):
                break
        if isinstance(help_target, dict):
            parent_name = " ".join(path)
            return (
                f"Subcommands of !!/{parent_name} are: {", ".join(help_target.keys())}"
            )

        doc = help_target.__doc__ if help_target.__doc__ is not None else "(no help)"
        parameters = []
        for parameter_name, parameter in inspect.signature(
            help_target
        ).parameters.items():
            if parameter_name in IGNORED_PARAMETERS:
                continue
            if isinstance(parameter.annotation, EnumType):
                values = "/".join(
                    item.value
                    for item in list(parameter.annotation)
                    if isinstance(item, Enum)
                )
                body = f"ENUM {parameter_name}: {values}"
            elif isinstance(parameter.annotation, UnionType):
                body = f"{ARGUMENT_TYPE_SIGNATURES[parameter.annotation.__args__[0]].name} {parameter_name}"
            else:
                body = f"{ARGUMENT_TYPE_SIGNATURES[parameter.annotation].name} {parameter_name}"
            if parameter.default != parameter.empty:
                if parameter.default == None:
                    parameters.append(f"[{body}]")
                else:
                    default = (
                        parameter.default.value
                        if isinstance(parameter.default, Enum)
                        else repr(parameter.default)
                    )
                    parameters.append(f"[{body} = {default}]")
            else:
                parameters.append(f"({body})")
        return f"`!!/{name} {" ".join(parameters)}`: {doc}"

    async def commands_command(self):
        """List all commands supported by the bot."""
        return f"All commands: {", ".join(self.commands.keys())}"

    # Fun commands

    class StatusMood(Enum):
        NORMAL = "normal"
        TINGLY = "tingly"

    async def status_command(self, mood: StatusMood = StatusMood.NORMAL):
        """Display "status information"."""
        status = random.choice(STATUSES)
        match mood:
            case Commands.StatusMood.NORMAL:
                return status
            case Commands.StatusMood.TINGLY:
                return Uwuipy().uwuify(status)

    async def coffee_command(self, target: str | None = None):
        """Brew some coffee."""
        if target is None:
            return "☕"
        else:
            return f"@{target} ☕"

    async def maul_command(self, target: str, *, event: MessageEvent):
        """SUMMON THE RAPTORS"""
        if re.fullmatch(r"me|(vyxal ?bot\d*)", target, re.IGNORECASE) is not None:
            return RAPTOR.format(user=event.user_name.capitalize()), None
        else:
            return RAPTOR.format(user=target.capitalize()), None

    async def hug_command(self, target: str | None = None):
        """<3"""
        if target is None:
            return random.choice(HUGS)
        else:
            return f"*gives @{target} a hug.* {random.choice(HUGS)}"

    async def sus_command(self):
        """STOP POSTING ABOUT AMONG US"""
        return "ඞ" * random.randint(8, 64)

    async def amilyxal_command(self, *, event: MessageEvent):
        """Check if you are lyxal."""
        return f"You are {"" if (event.user_id == 354515) != (random.random() <= 0.1) else "not "}lyxal."

    async def cookie_command(self):
        """Bake a cookie. Maybe. You have to be worthy."""
        if random.random() <= 0.75:
            return "Here you go: 🍪"
        else:
            return "No."

    async def party_command(self):
        """🎉"""
        return "".join(random.choice("🎉🎊🥳🎈") for _ in range(15))

    # Group and user commands

    async def resolve_user(self, target: str):
        if target.isnumeric():
            if (
                target_user := await self.db.user.find_unique(
                    where={"id": int(target)}, include={"groups": True}
                )
            ) is None:
                return f"I don't know of a user with the ID `{target}`."
            return target_user
        else:
            match (
                await self.db.user.find_many(
                    where={"name": target}, include={"groups": True}
                )
            ):
                case []:
                    return f'I don\'t know of any users named "{target}".'
                case [single]:
                    return single
                case [*multiple]:
                    return (
                        f"I know of multiple users named {target}: "
                        f"{", ".join(f"{user.name} ({user.id})" for user in multiple)}"
                        f". Please run this command again and supply the ID of the user you wish to look up."
                    )

    def can_user_manage(self, user: User, group: Group):
        assert user.groups is not None
        if any(group.group_name == ADMIN_GROUP for group in user.groups):
            return True, None
        assert group.is_managed_by is not None
        if len(group.is_managed_by) and not len(
            set(group.is_managed_by) & set(user.groups)
        ):
            return False, (
                f"You are not allowed to modify this group. Only members of groups "
                f"{" | ".join(f"_{group.name}_" for group in group.is_managed_by)} "
                f"are allowed to do that."
            )
        return True, None

    async def user_info_command(self, target: str | None = None, *, current_user: User):
        """Fetch information about a user, yourself by default."""
        if target is None:
            target_user = current_user
        else:
            match (await self.resolve_user(target)):
                case str(error):
                    return error
                case User() as target_user:
                    pass
        assert target_user.groups is not None
        group_names = (
            ", ".join(
                group.group_name + (" (protected)" if group.protected else "")
                for group in target_user.groups
            )
            if len(target_user.groups)
            else "(none)"
        )
        return (
            f"User information of {target_user.name} ({target_user.id}):\n"
            f"- Member of groups: {group_names}"
        )

    async def group_create_command(self, name: str, can_manage: list[str] = [], *, current_user: User):
        """Create a new group."""
        if (await self.db.group.find_unique(where={"name": name})) is not None:
            return f"There is already a group named _{name}_."
        for group_name in can_manage:
            group = await self.db.group.find_unique(where={"name": group_name}, include={"is_managed_by": True})
            if group is None:
                return f"There is no group named _{name}_."
            if not self.can_user_manage(current_user, group)[0]:
                return f"You are not allowed to manage _{group}_."
        await self.db.group.create(
            data={
                "name": name,
                "members": {},
                "allowed_commands": {},
                "can_manage": {
                    "connect": [{"name": name} for name in can_manage],
                },
            }
        )
        return f"Group _{name}_ created."

    async def group_delete_command(self, name: str, *, current_user: User):
        """Delete a group."""
        if (
            group := await self.db.group.find_unique(
                where={"name": name}, include={"is_managed_by": True, "members": True}
            )
        ) is None:
            return f"There is no group named _{name}_."
        assert group.members is not None
        match self.can_user_manage(current_user, group):
            case (True, _):
                pass
            case (False, str(error)):
                return error
        if any(member.protected for member in group.members):
            return f"Group _{name}_ has protected members and may not be deleted."
        await self.db.group.delete(where={"name": name})
        return f"Group _{name}_ has been deleted."

    async def group_info_command(self, name: str):
        """Fetch member and command information for a group."""
        group = await self.db.group.find_unique(
            where={"name": name},
            include={
                "members": {"include": {"user": True}},
                "allowed_commands": True,
                "is_managed_by": True,
                "can_manage": True,
            },
        )
        if group is None:
            return f"There is no group named _{name}_."

        assert group.members is not None
        members = (
            ", ".join(cast(User, member.user).name for member in group.members)
            if len(group.members)
            else "(none)"
        )
        assert group.allowed_commands is not None
        allowed_commands = (
            ", ".join(command.command for command in group.allowed_commands)
            if len(group.allowed_commands)
            else "(none)"
        )
        assert group.is_managed_by is not None
        is_managed_by = (
            " | ".join(group.name for group in group.is_managed_by)
            if len(group.allowed_commands)
            else "(none)"
        )
        assert group.can_manage is not None
        can_manage = (
            " | ".join(group.name for group in group.can_manage)
            if len(group.can_manage)
            else "(none)"
        )
        return (
            f"Group information for {name}:\n"
            f"- Members: {members}\n"
            f"- Allowed commands: {allowed_commands}"
            f"- Managed by: {is_managed_by}"
            f"- Can manage: {can_manage}"
        )

    class MembershipAction(Enum):
        ADD = "add"
        REMOVE = "remove"

    async def group_member_command(
        self,
        name: str,
        action: MembershipAction,
        target: str | None = None,
        *,
        current_user: User,
    ):
        """Add or remove a user from a group, yourself by default."""
        if (
            group := await self.db.group.find_unique(
                where={"name": name}, include={"is_managed_by": True}
            )
        ) is None:
            return f"There is no group named _{name}_."
        assert current_user.groups is not None
        assert group.is_managed_by is not None
        match self.can_user_manage(current_user, group):
            case (True, _):
                pass
            case (False, str(error)):
                return error
        if target is None:
            target_user = current_user
        else:
            match (await self.resolve_user(target)):
                case User() as target_user:
                    pass
                case str(error):
                    return error

        current_membership = await self.db.groupmembership.find_unique(
            where={
                "user_id_group_name": {"user_id": target_user.id, "group_name": name}
            }
        )
        match action:
            case Commands.MembershipAction.ADD:
                if current_membership is not None:
                    return (
                        f"{"You are" if target_user == current_user else f"{target_user.name} is"} "
                        f"already a member of group _{name}_."
                    )
                await self.db.groupmembership.create(
                    data={
                        "group": {"connect": {"name": name}},
                        "user": {"connect": {"id": target_user.id}},
                    }
                )
                return f"Added {"you" if target_user == current_user else target_user.name} to group _{name}_."
            case Commands.MembershipAction.REMOVE:
                if current_membership is None:
                    return (
                        f"{"You are" if target_user == current_user else f"{target_user.name} is"} "
                        f"not a member of group _{name}_."
                    )
                if current_membership.protected:
                    return f"{target_user.name} may not be removed from group _{name}_."
                await self.db.groupmembership.delete(
                    where={
                        "user_id_group_name": {
                            "group_name": name,
                            "user_id": target_user.id,
                        }
                    }
                )
                return f"Removed {"you" if target_user == current_user else target_user.name} from group _{name}_."

    async def group_manager_command(
        self, target: str, action: MembershipAction, manager: str, *, current_user: User
    ):
        """Change which other groups are allowed to manage a group."""
        if (
            target_group := await self.db.group.find_unique(
                where={"name": target}, include={"is_managed_by": True}
            )
        ) is None:
            return f"There is no group named _{target}_."
        if (
            manager_group := await self.db.group.find_unique(where={"name": manager})
        ) is None:
            return f"There is no group named _{manager}_."
        assert current_user.groups is not None
        assert target_group.is_managed_by is not None

        match self.can_user_manage(current_user, manager_group):
            case (True, _):
                pass
            case (False, str(error)):
                return error
        match self.can_user_manage(current_user, target_group):
            case (True, _):
                pass
            case (False, str(error)):
                return error

        match action:
            case Commands.MembershipAction.ADD:
                if manager_group in target_group.is_managed_by:
                    return f"_{manager}_ is already managing _{target}_."
                await self.db.group.update(
                    data={"is_managed_by": {"connect": [{"name": manager}]}},
                    where={"name": target},
                )
                return f"_{manager}_ is now managing _{target}_."
            case Commands.MembershipAction.REMOVE:
                if manager_group not in target_group.is_managed_by:
                    return f"_{manager}_ is not managing _{target}_."
                await self.db.group.update(
                    data={"is_managed_by": {"disconnect": [{"name": manager}]}},
                    where={"name": target},
                )
                return f"_{manager}_ is no longer managing _{target}_."

    async def command_permission_command(
        self, command: str, action: MembershipAction, group: str
    ):
        """Change which groups are allowed to run a command."""
        if (
            await self.db.group.find_unique(
                where={"name": group}, include={"is_managed_by": True}
            )
            is None
        ):
            return f"There is no group named _{group}_."

        current_groups = [
            permission.group_name
            for permission in await self.db.commandpermission.find_many(
                where={"command": command}
            )
        ]
        match action:
            case Commands.MembershipAction.ADD:
                if group in current_groups:
                    return f"`!!/{command}` is already usable by _{group}_."
                await self.db.commandpermission.create(
                    data={"command": command, "group": {"connect": {"name": group}}}
                )
                return f"`!!/{command}` is now usable by _{group}_."
            case Commands.MembershipAction.REMOVE:
                if group not in current_groups:
                    return (
                        f"`!!/{command}` is already not explicitly usable by _{group}_."
                    )
                await self.db.commandpermission.delete(
                    where={
                        "command_group_name": {"command": command, "group_name": group}
                    }
                )
                return f"`!!/{command}` is no longer explicitly usable by _{group}_."

    async def command_permissions_command(self, command: str):
        """Check which groups are allowed to run a command."""
        permissions = await self.db.commandpermission.find_many(where={"command": command})
        if not len(permissions):
            return f"`!!/{command}` is usable by everybody."
        return f"`!!/{command}` is usable by groups {" | ".join(f"_{permission.group_name}_" for permission in permissions)}."
    
    # Utility commands

    async def ping(self, group_name: str, message: str | None = None):
        """Ping every member of a group. Use this feature with caution."""
        if (
            group := await self.db.group.find_unique(
                where={"name": group_name}, include={"members": {"include": {"user": True}}}
            )
        ) is None:
            return f"There is no group named _{group_name}_."
        assert group.members is not None
        if not len(group.members):
            return "Nobody to ping."
        ping = " ".join(f"@{cast(User, membership.user).name.replace(" ", "")}" for membership in group.members)
        if message is not None:
            return f"{ping} {message}"
        return ping