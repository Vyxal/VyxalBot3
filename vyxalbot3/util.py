import inspect
from datetime import datetime
from typing import Any, Awaitable, Callable, Coroutine, overload


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
