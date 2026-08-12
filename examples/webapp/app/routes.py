"""Runtime dispatch: routes map paths to handler *names*.

`getattr(handlers, name)` is invisible to static analysis — a handler can be
unmounted here and no scanner will ever notice. The unmounted-handler
resolver in test_ratchet.py notices.
"""

from app import handlers

ROUTES = {
    "/": "handle_home",
    "/login": "handle_login",
}


def dispatch(path: str) -> str:
    return getattr(handlers, ROUTES[path])()
