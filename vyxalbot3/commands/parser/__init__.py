import os.path
from enum import Enum, auto
from typing import Literal

from lark import Lark, Transformer, UnexpectedCharacters, UnexpectedInput


class ArgumentType(Enum):
    FLAG = auto()
    STRING = auto()
    FLOAT = auto()
    INT = auto()
    STRARRAY = auto()


type Argument = (
    tuple[Literal[ArgumentType.FLAG], str]
    | tuple[Literal[ArgumentType.STRING], str]
    | tuple[Literal[ArgumentType.FLOAT], float]
    | tuple[Literal[ArgumentType.INT], int]
    | tuple[Literal[ArgumentType.STRARRAY], list[str]]
)


class ParseError(Exception):
    def __init__(self, message: str):
        super().__init__()
        self.message = message


class ArgumentTransformer(Transformer):
    def bareword(self, value):
        return (ArgumentType.FLAG, str(value[0]))

    def string(self, value):
        return (ArgumentType.STRING, str(value[0][1:-1]))

    def float(self, value):
        return (ArgumentType.FLOAT, float(value[0]))

    def int(self, value):
        return (ArgumentType.INT, int(value[0]))

    def strarray(self, value):
        return (ArgumentType.STRARRAY, list(item[1:-1] for item in value))

    def explicit_argument(self, value):
        return str(value[0]), value[1]

    def command(self, value):
        return value[0].children, dict(value[1].children)


with open(os.path.join(os.path.split(__file__)[0], "grammar.lark")) as file:
    parser = Lark(file, start="command")


def parse_arguments(arguments: str) -> tuple[list[Argument], dict[str, Argument]]:
    try:
        return ArgumentTransformer().transform(parser.parse(arguments))
    except UnexpectedInput as error:
        message = error.match_examples(
            parser.parse,
            {
                "Unclosed string": ["""help "foo"""],
                "Malformed number": ["help 123.", "help .456", "help ."],
                "Unclosed strarray": ["help [a b c"],
            },
        )
        if message is not None:
            raise ParseError(message) from error
        if isinstance(error, UnexpectedCharacters):
            raise ParseError(f"Unexpected toplevel character {error.char}") from error
        raise ParseError(str(error)) from error
