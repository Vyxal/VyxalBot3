from enum import Enum, auto
from string import digits, ascii_letters
from inspect import signature
from typing import Generator, Literal

class ParseState(Enum):
    TOPLEVEL = auto()
    FLAG = auto()
    STRING = auto()
    NUMBER = auto()
    STRARRAY = auto()


class ArgumentType(Enum):
    FLAG = auto()
    STRING = auto()
    FLOAT = auto()
    INT = auto()
    STRARRAY = auto()
    ERROR = auto()

type Argument = (
    tuple[Literal[ArgumentType.FLAG], str]
    | tuple[Literal[ArgumentType.STRING], str]
    | tuple[Literal[ArgumentType.FLOAT], float]
    | tuple[Literal[ArgumentType.INT], int]
    | tuple[Literal[ArgumentType.STRARRAY], list[str]]
    | tuple[Literal[ArgumentType.ERROR], str]
)

class ParseError(Exception):
    def __init__(self, message: str):
        super().__init__()
        self.message = message

def parse_arguments(arguments: str) -> Generator[Argument]:
    characters = list(arguments)
    stack = []
    state = ParseState.TOPLEVEL
    while True:
        match state:
            case ParseState.TOPLEVEL:
                try:
                    char = characters.pop(0)
                except IndexError:
                    return
                if char in ascii_letters:
                    state = ParseState.FLAG
                    stack.append(char)
                elif char in digits:
                    state = ParseState.NUMBER
                    stack.append(char)
                elif char == '"':
                    state = ParseState.STRING
                elif char == "[":
                    state = ParseState.STRARRAY
                    stack.append([])
                elif char == " ":
                    pass
                else:
                    yield ArgumentType.ERROR, f"Unexpected toplevel character {char}"
                    return
            case ParseState.FLAG:
                try:
                    char = characters.pop(0)
                except IndexError:
                    char = " "
                if char == " ":
                    yield ArgumentType.FLAG, "".join(stack)
                    stack.clear()
                    state = ParseState.TOPLEVEL
                else:
                    stack.append(char)
            case ParseState.STRING:
                try:
                    char = characters.pop(0)
                except IndexError:
                    yield ArgumentType.ERROR, "Unclosed string"
                    return
                if char == "\\":
                    try:
                        stack.append(characters.pop(0))
                    except IndexError:
                        yield ArgumentType.ERROR, "Expected character to escape"
                        return
                elif char == '"':
                    yield ArgumentType.STRING, "".join(stack)
                    stack.clear()
                    state = ParseState.TOPLEVEL
                else:
                    stack.append(char)
            case ParseState.NUMBER:
                try:
                    char = characters.pop(0)
                except IndexError:
                    char = None
                else:
                    if char in digits:
                        stack.append(char)
                    elif char == ".":
                        stack.append(char)
                        try:
                            stack.append(characters.pop(0))
                        except IndexError:
                            yield ArgumentType.ERROR, "Expected digit after period"
                            return
                    elif char == " ":
                        char = None
                    else:
                        yield ArgumentType.ERROR, "Expected digit or period"
                        return
                if char == None:
                    if "." in stack:
                        yield ArgumentType.FLOAT, float("".join(stack))
                    else:
                        yield ArgumentType.INT, int("".join(stack))
                    stack.clear()
                    state = ParseState.TOPLEVEL
            case ParseState.STRARRAY:
                while True:
                    try:
                        char = characters.pop(0)
                    except IndexError:
                        yield ArgumentType.ERROR, "Unclosed strarray"
                        return
                    if char == "\\":
                        try:
                            stack[-1].append(characters.pop(0))
                        except IndexError:
                            yield ArgumentType.ERROR, "Expected character to escape"
                            return
                    elif char == ",":
                        stack.append([])
                        break
                    elif char == "]":
                        yield ArgumentType.STRARRAY, [
                            "".join(i) for i in stack if len(i)
                        ]
                        stack.clear()
                        state = ParseState.TOPLEVEL
                        break
                    else:
                        stack[-1].append(char)