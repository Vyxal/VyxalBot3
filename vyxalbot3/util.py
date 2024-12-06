from datetime import datetime
import inspect
from typing import Awaitable, Callable, Coroutine, overload, Any


# class autocache[**P, R]:
#     type Value = tuple[datetime, R]
#     def __init__(self, method: Callable[P, Value | Coroutine[Any, Any, Value]]):
#         self._method = method
#         self._value: "autocache.Value | None" = None

#     @property
#     def expires(self):
#         return self._value[1] if self._value is not None else None

#     async def _store(self, value: Awaitable[Value]) -> R:
#         self._value = await value
#         return self._value[1]

#     @overload
#     def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
#         ...

#     @overload
#     async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
#         ...

#     def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R | Awaitable[R]:
#         if self._value is None or self._value[0] < datetime.now():
#             ret = self._method(*args, **kwargs)
#             if inspect.isawaitable(ret):
#                 return self._store(ret)
#             self._value = ret
#         return self._value[1]


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
