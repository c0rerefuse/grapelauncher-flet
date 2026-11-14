import threading
from typing import cast

import flet as ft

from app_styles import ButtonStyles
from app_styles.configurator import Configurator

from minecraft_utils import MinecraftRunner, MinecraftVersion

from http_actions import get_all_versions
from http_actions.models import ServerData


PROGRESS_HEIGHT = 60


def main(page: ft.Page):
    page.title = "GrapeLauncher"
    page.padding = 0

    page.theme_mode = Configurator.get_theme_mode()
    page.bgcolor = Configurator.get_color("background", "#121214")

    page.fonts = {"base": "fonts/base_text.otf"}
    page.theme = ft.Theme(
        font_family="base",
        color_scheme=ft.ColorScheme(
            surface=Configurator.get_color("background"),
            on_surface=Configurator.get_color("text_primary"),
        ),
    )

    text_primary = Configurator.get_color("text_primary")
    text_secondary = Configurator.get_color("text_secondary")
    icon_color = Configurator.get_color("icon_color")
    border_color = Configurator.get_color("border")

    accent = Configurator.get_color("accent", "#7c5cff")
    accent_alt = Configurator.get_color("accent_alt", "#a78bfa")

    available_versions = get_all_versions()

    selected_version = ft.Text(
        available_versions[0].name,
        size=14,
        color=text_primary,
        data=available_versions[0]
    )

    def select_version(e):
        selected_version.value = f"{e.control.content}"
        selected_version.data = f"{e.data}"
        page.update()

    version_popup = ft.PopupMenuButton(
        bgcolor=Configurator.get_color("sidebar_bg"),
        content=ft.Container(
            content=ft.Row(
                [
                    selected_version,
                    ft.Icon(ft.icons.Icons.KEYBOARD_ARROW_UP, color=icon_color),
                ],
                spacing=5,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border=ft.Border.all(1, border_color),
            border_radius=8,
        ),
        items=[
            ft.PopupMenuItem(content=i.name, on_click=select_version, data=i)
            for i in available_versions
        ],
    )

    sidebar = ft.Container(
        width=70,
        bgcolor=Configurator.get_color("sidebar_bg"),
        padding=ft.Padding.symmetric(vertical=15),
        content=ft.Column(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=15,
                    controls=[
                        ft.IconButton(icon=ft.icons.Icons.HOME_OUTLINED, icon_color=icon_color, tooltip="Главная"),
                        ft.IconButton(icon=ft.icons.Icons.FOLDER_OUTLINED, icon_color=icon_color, tooltip="Сборки"),
                        ft.IconButton(icon=ft.icons.Icons.EXTENSION_OUTLINED, icon_color=icon_color, tooltip="Моды"),
                    ],
                ),
                ft.IconButton(icon=ft.icons.Icons.SETTINGS_OUTLINED, icon_color=icon_color, tooltip="Настройки"),
            ],
        ),
    )

    main_content = ft.Container(
        expand=True,
        bgcolor=Configurator.get_color("background"),
        padding=25,
        content=ft.Column(
            controls=[
                ft.Text("Новости и обновления", size=24, weight=ft.FontWeight.BOLD, color=text_primary),
                ft.Text("Здесь будет основной контент лаунчера...", size=16, color=text_secondary),
            ]
        ),
    )

    upper_area = ft.Row(expand=True, spacing=0, controls=[sidebar, main_content])

    # ============================================================
    #                   ПРОГРЕСС УСТАНОВКИ
    # ============================================================

    install_bar = ft.ProgressBar(
        value=0, color=accent, bgcolor=border_color, height=4, border_radius=2,
    )
    stage_bar = ft.ProgressBar(
        value=0, color=accent_alt, bgcolor=border_color, height=4, border_radius=2,
    )

    install_label = ft.Text("Загрузка...", size=11, color=text_secondary)
    install_percent = ft.Text("0%", size=11, color=text_secondary)
    stage_label = ft.Text("", size=11, color=text_secondary)
    stage_percent = ft.Text("0%", size=11, color=text_secondary)

    progress_column = ft.Column(
        spacing=4,
        tight=True,
        controls=[
            ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[install_label, install_percent]),
            install_bar,
            ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[stage_label, stage_percent]),
            stage_bar,
        ],
    )

    # ✅ Исправлено: ft.Offset вместо ft.transform.Offset
    progress_section = ft.Container(
        height=0,
        animate_size=ft.Animation(400, ft.AnimationCurve.EASE_OUT),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Container(
            height=PROGRESS_HEIGHT,
            offset=ft.Offset(0, 1),        # ← было ft.transform.Offset(0, 1)
            opacity=0,
            animate_offset=ft.Animation(400, ft.AnimationCurve.EASE_OUT),
            animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_OUT),
            padding=ft.Padding.only(top=8, bottom=8),
            content=progress_column,
        ),
    )

    def show_progress(install_text: str = "Подготовка...", stage_text: str = ""):
        install_label.value = install_text
        stage_label.value = stage_text
        install_percent.value = "0%"
        stage_percent.value = "0%"
        install_bar.value = 0
        stage_bar.value = 0

        progress_section.content.opacity = 1
        progress_section.content.offset = ft.Offset(0, 0)   # ← было ft.transform.Offset(0, 0)
        progress_section.height = PROGRESS_HEIGHT
        page.update()

    def hide_progress():
        progress_section.content.opacity = 0
        progress_section.content.offset = ft.Offset(0, 1)   # ← было ft.transform.Offset(0, 1)
        progress_section.height = 0
        page.update()

    def set_install(value: float, text: str | None = None):
        install_bar.value = max(0.0, min(1.0, value))
        install_percent.value = f"{int(install_bar.value * 100)}%"
        if text is not None:
            install_label.value = text
        page.update()

    def set_stage(value: float, text: str | None = None):
        stage_bar.value = max(0.0, min(1.0, value))
        stage_percent.value = f"{int(stage_bar.value * 100)}%"
        if text is not None:
            stage_label.value = text
        page.update()

    # ============================================================
    #                     ЗАПУСК ИГРЫ (с реальным прогрессом)
    # ============================================================

    def run_game():
        svd = cast(ServerData, selected_version.data)
        mv = MinecraftVersion(
            version=svd.mc_ver,
            provider=svd.provider,
            server_name=svd.name,
            java_version=svd.java_ver,
        )

        show_progress("Подготовка установки...", "Инициализация")

        current_max = 0

        def set_status(text: str):
            set_stage(stage_bar.value, text)
            if "Java" in text:
                set_install(0.15, text)
            elif "Minecraft" in text:
                set_install(0.45, text)
            elif "Запуск" in text:
                set_install(0.9, text)

        def set_progress(value: int):
            if current_max > 0:
                set_stage(value / current_max)

        def set_max(value: int):
            nonlocal current_max
            current_max = value

        callback = {
            "setStatus": set_status,
            "setProgress": set_progress,
            "setMax": set_max,
        }

        def worker():
            try:
                MinecraftRunner.play(mv, callback)
                set_install(1.0, "Готово")
            except Exception as ex:
                set_stage(0, f"Ошибка: {ex}")
                return
            finally:
                threading.Timer(0.6, hide_progress).start()

        page.run_thread(worker)

    play_button = ft.Button(
        content="Играть",
        style=ButtonStyles.a,
        icon=ft.icons.Icons.PLAY_ARROW_OUTLINED,
        on_click=lambda e: run_game(),
    )

    bottom_bar = ft.Container(
        bgcolor=Configurator.get_color("bottom_bar_bg"),
        padding=ft.Padding.symmetric(horizontal=20),
        content=ft.Column(
            spacing=0,
            tight=True,
            controls=[
                progress_section,
                ft.Container(
                    height=75,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[version_popup, play_button],
                    ),
                ),
            ],
        ),
    )

    page.add(
        ft.Column(
            expand=True,
            spacing=0,
            controls=[upper_area, bottom_bar],
        )
    )


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")