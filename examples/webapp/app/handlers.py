"""Request handlers. Dispatched dynamically *by name* — see routes.py.

That dynamic dispatch is exactly what static dead-code analysis cannot see:
vulture reports every handler here as unused. The baseline accepts those
findings with a written reason instead of silencing the scanner.
"""

from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates"


def render(template_name: str) -> str:
    return (TEMPLATES / template_name).read_text(encoding="utf-8")


def handle_home() -> str:
    return render("home.html")


def handle_login() -> str:
    return render("login.html")


def handle_export() -> str:
    # Written ahead of the admin panel; nothing mounts it yet.
    return "id,name\n"
