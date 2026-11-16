import json
from pathlib import Path
import flet as ft


class Configurator:
    current_dir = Path(__file__).parent
    json_path = current_dir / "app_theme.json"
    with open(json_path, "r", encoding="utf-8") as file: 
        theme_data = json.load(file)

    colors = theme_data.get("colors", {})
    buttons_theme = theme_data.get("buttons", {})

    @classmethod
    def get_theme_mode(cls) -> ft.ThemeMode:
        mode = cls.theme_data.get("theme_mode", "dark").lower()
        return ft.ThemeMode.LIGHT if mode == "light" else ft.ThemeMode.DARK

    @classmethod
    def get_color(cls, key: str, default: str = "#ffffff") -> str:
        return cls.colors.get(key, default)
