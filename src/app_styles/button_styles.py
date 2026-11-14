import flet as ft

from .configurator import Configurator


class ButtonStyles:
    _a = Configurator.buttons_theme.get("a", {})
    a = ft.ButtonStyle(
        color=_a.get("color", "#e3e3e3"),
        bgcolor=_a.get("bgcolor", "#7f02b5"),
    )
