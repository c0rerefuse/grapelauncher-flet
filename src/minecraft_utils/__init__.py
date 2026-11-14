import os
import uuid
import sys
import subprocess
import traceback
import logging
import threading
from datetime import datetime

import flet as ft
import minecraft_launcher_lib as mll

from .models import MinecraftProvider, MinecraftVersion
from .mc_installer import MinecraftInstaller
from .java_installer import JavaInstaller


# ============================================================
# ЛОГИРОВАНИЕ: файл + консоль
# ============================================================
LOG_FILE = os.path.abspath(os.path.join(os.getcwd(), "mc_debug.log"))

_logger = logging.getLogger("MC-DEBUG")
_logger.setLevel(logging.DEBUG)
_logger.propagate = False
for _h in list(_logger.handlers):
    _logger.removeHandler(_h)

_fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
_logger.addHandler(_fh)

try:
    _ch = logging.StreamHandler(sys.stdout or sys.__stdout__)
    _ch.setLevel(logging.DEBUG)
    _ch.setFormatter(logging.Formatter("[MC-DEBUG] %(message)s"))
    _logger.addHandler(_ch)
except Exception:
    pass


def _log(*args):
    try:
        _logger.info(" ".join(str(a) for a in args))
    except Exception:
        try:
            print("[MC-DEBUG]", *args, flush=True)
        except Exception:
            pass


_log("=" * 70)
_log("=== НАЧАЛО СЕССИИ ЛОГА:", LOG_FILE)
_log("Время:", datetime.now().isoformat())
_log("=" * 70)


class MinecraftRunner:
    # ---------- Java ----------
    @staticmethod
    def _find_java_exe(java_path: str, java_version: str) -> str | None:
        """Ищет java.exe / java в base_path/java/*<java_version>*/..."""
        if not os.path.isdir(java_path):
            _log("_find_java_exe: папка не существует:", java_path)
            return None
        try:
            entries = os.listdir(java_path)
        except OSError as e:
            _log("_find_java_exe: ошибка чтения папки:", repr(e))
            return None

        _log("_find_java_exe: содержимое", java_path, "=", entries)

        for name in entries:
            if java_version in name:
                candidate_dir = os.path.join(java_path, name)
                _log("_find_java_exe: смотрим в", candidate_dir)
                for root, _dirs, files in os.walk(candidate_dir):
                    for f in files:
                        if f in ("java", "java.exe"):
                            full = os.path.join(root, f)
                            _log("_find_java_exe: найден java:", full)
                            return full

        _log("_find_java_exe: бинарник java для версии", java_version, "не найден")
        return None

    # ---------- Диагностика ----------
    @staticmethod
    def _dump_command(command: list[str]) -> None:
        _log("ПОЛНАЯ КОМАНДА ЗАПУСКА (%d аргументов):", len(command))
        skip_next = False
        for i, arg in enumerate(command):
            if skip_next:
                skip_next = False
                continue

            if arg in ("-cp", "-classpath"):
                _log(f"  [{i:03d}] {arg}")
                if i + 1 < len(command):
                    cp = command[i + 1]
                    parts = cp.split(os.pathsep)
                    _log(f"  [{i + 1:03d}] classpath ({len(parts)} элементов):")
                    for p in parts:
                        mark = "OK  " if os.path.exists(p) else "MISS"
                        _log(f"          [{mark}] {p}")
                    skip_next = True
            else:
                _log(f"  [{i:03d}] {arg!r}")

    @staticmethod
    def _pump_stdout(proc: subprocess.Popen) -> None:
        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    _log("MC:", line.rstrip())
            code = proc.wait()
            _log("Minecraft завершился с кодом:", code)
        except Exception as e:
            _log("_pump_stdout: ошибка при чтении вывода игры:", repr(e))
            _log(traceback.format_exc())

    # ---------- Запуск ----------
    @staticmethod
    def play(mv: MinecraftVersion, callback: dict | None = None):
        _log("=" * 60)
        _log("play() ВЫЗВАН")
        _log("=" * 60)

        try:
            # --- 0. Данные о версии ---
            _log("mv:", mv)
            _log("mv.version:", getattr(mv, "version", "<нет>"))
            _log("mv.provider:", getattr(mv, "provider", "<нет>"))
            _log("mv.java_version:", getattr(mv, "java_version", "<нет>"))
            _log("mv.server_name:", getattr(mv, "server_name", "<нет>"))

            if callback is None:
                callback = {}
            _log("callback keys:", list(callback.keys()))

            # --- 1. Базовые пути ---
            _log("Шаг 1: получаем base_path через MinecraftInstaller.get_path()...")
            try:
                base_path = MinecraftInstaller.get_path()
            except Exception as e:
                _log("!!! ОШИБКА в get_path():", repr(e))
                _log(traceback.format_exc())
                raise

            _log("base_path =", repr(base_path))
            _log("base_path absolute =", repr(os.path.abspath(base_path)))

            java_path = os.path.join(base_path, "java")
            _log("java_path =", repr(java_path))

            # --- 2. Создание папок ---
            os.makedirs(base_path, exist_ok=True)
            os.makedirs(java_path, exist_ok=True)
            _log("base_path существует:", os.path.exists(base_path))
            _log("java_path существует:", os.path.exists(java_path))

            # --- 3. Проверка / установка Java ---
            _log("Шаг 3: проверяем наличие Java в", repr(java_path))
            java_installed = False
            try:
                contents = os.listdir(java_path)
                _log("содержимое java_path:", contents)
                for item in contents:
                    if mv.java_version in item:
                        java_installed = True
                        _log("найдена Java:", item)
                        break
            except Exception as e:
                _log("!!! ОШИБКА при чтении java_path:", repr(e))
                _log(traceback.format_exc())
                raise

            _log("java_installed =", java_installed)
            if not java_installed:
                _log("Шаг 3: устанавливаем Java...")
                if "setStatus" in callback:
                    callback["setStatus"]("Установка Java...")
                try:
                    JavaInstaller.install_java(mv)
                except Exception as e:
                    _log("!!! ОШИБКА в JavaInstaller.install_java:", repr(e))
                    _log(traceback.format_exc())
                    raise
                _log("Java установлена. Содержимое java_path:", os.listdir(java_path))
            else:
                _log("Java уже установлена, пропускаем установку")

            # --- 3.1. Находим java.exe (только чтобы передать путь, не экспортируем в PATH) ---
            java_exe = MinecraftRunner._find_java_exe(java_path, mv.java_version)
            if java_exe:
                _log("Используемая Java:", java_exe)
            else:
                _log("!!! ВНИМАНИЕ: java.exe не найден, полагаемся на системный java")

            # --- 4. Установка Minecraft ---
            install_dir = base_path  # для vanilla совпадает с base_path
            launch_version_id = mv.version

            if mv.provider == MinecraftProvider.VANILLA:
                _log("Шаг 4: VANILLA, ставим через mll.install...")
                if "setStatus" in callback:
                    callback["setStatus"]("Установка Minecraft (vanilla)...")
                try:
                    mll.install.install_minecraft_version(
                        mv.version,
                        base_path,
                        callback=callback,
                    )
                except Exception as e:
                    _log("!!! ОШИБКА в install_minecraft_version:", repr(e))
                    _log(traceback.format_exc())
                    raise
                _log("Minecraft (vanilla) установлен")
            else:
                _log("Шаг 4: модовый провайдер =", mv.provider)
                if "setStatus" in callback:
                    callback["setStatus"]("Установка модового Minecraft...")

                # Передаём java явно в MinecraftInstaller
                try:
                    error, install_dir = MinecraftInstaller.install_minecraft(
                        mv, callback, java=java_exe
                    )
                except Exception as e:
                    _log("!!! ОШИБКА в MinecraftInstaller.install_minecraft:", repr(e))
                    _log(traceback.format_exc())
                    raise

                _log("MinecraftInstaller.install_minecraft вернул: error =", error, "install_dir =", install_dir)
                if error:
                    _log("!!! InstallerError:", error.error, "level=", error.level)
                    raise RuntimeError(error.error)

                if not install_dir:
                    raise RuntimeError(
                        "MinecraftInstaller не вернул install_dir — "
                        "невозможно определить папку для запуска."
                    )

                # Получаем launch_version_id (ID установленного модлоадера)
                _log("Шаг 4: получаем mod_loader для", mv.provider.value)
                try:
                    mod_loader = mll.mod_loader.get_mod_loader(mv.provider.value)
                    loader_version = mod_loader.get_latest_loader_version(mv.version)
                    _log("loader_version =", loader_version)
                    launch_version_id = mod_loader.get_installed_version(
                        mv.version, loader_version
                    )
                except Exception as e:
                    _log("!!! ОШИБКА при получении mod_loader:", repr(e))
                    _log(traceback.format_exc())
                    raise
                _log("launch_version_id (модовый) =", launch_version_id)

            _log("Шаг 4: итоговый launch_version_id =", launch_version_id)
            _log("Шаг 4: итоговый install_dir =", install_dir)

            # --- 4.1. Проверка файлов версии внутри install_dir ---
            version_dir = os.path.join(install_dir, "versions", launch_version_id)
            version_json = os.path.join(version_dir, f"{launch_version_id}.json")
            version_jar = os.path.join(version_dir, f"{launch_version_id}.jar")

            _log("version_dir:", version_dir, "exists:", os.path.exists(version_dir))
            _log("version_json:", version_json, "exists:", os.path.exists(version_json))
            _log("version_jar:", version_jar, "exists:", os.path.exists(version_jar))

            if not os.path.exists(version_json):
                raise RuntimeError(
                    f"Не найден JSON версии: {version_json}. "
                    f"Установка Minecraft не завершена в {install_dir}."
                )

            # --- 5. Запуск ---
            _log("Шаг 5: собираем команду запуска...")
            if "setStatus" in callback:
                callback["setStatus"]("Запуск игры...")

            options = {
                "username": "example",
                "uuid": str(uuid.uuid4()),
                "token": "mock_token_12345",
                "launcherName": "GrapeLauncher",
                "launcherVersion": "1.0",
            }

            # Если java.exe найден — передаём его через options,
            # чтобы get_minecraft_command использовал именно его.
            if java_exe:
                options["executablePath"] = java_exe
                options["defaultExecutablePath"] = java_exe

            _log("options =", options)

            try:
                command = mll.command.get_minecraft_command(
                    launch_version_id,
                    install_dir,  # ← ВАЖНО: та же папка, куда ставили модлоадер
                    options,
                )
            except Exception as e:
                _log("!!! ОШИБКА в get_minecraft_command:", repr(e))
                _log(traceback.format_exc())
                raise RuntimeError(f"Не удалось собрать команду запуска: {e}")

            _log("команда собрана, длина =", len(command))
            _log("command[0] из библиотеки:", repr(command[0]))
            try:
                _log("command[0] существует как файл:", os.path.exists(command[0]))
            except Exception:
                pass

            # На всякий случай: если библиотека проигнорировала executablePath,
            # принудительно подставляем наш java_exe первым аргументом.
            if java_exe and os.path.exists(java_exe):
                if not os.path.exists(command[0]):
                    _log(
                        "command[0] не существует, принудительно заменяем на",
                        java_exe,
                    )
                    command[0] = java_exe
                else:
                    _log("command[0] уже корректен, оставляем как есть")

            MinecraftRunner._dump_command(command)

            # --- 5.2. Запуск ---
            _log("Запускаем subprocess.Popen...")
            try:
                proc = subprocess.Popen(
                    command,
                    cwd=install_dir,  # ← рабочая директория игры = install_dir
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception as e:
                _log("!!! ОШИБКА в subprocess.Popen:", repr(e))
                _log(traceback.format_exc())
                raise RuntimeError(f"Не удалось запустить игру: {e}")

            _log("subprocess.Popen OK, pid =", proc.pid)

            threading.Thread(
                target=MinecraftRunner._pump_stdout,
                args=(proc,),
                daemon=True,
                name="mc-stdout-pump",
            ).start()

            _log("=" * 60)
            _log("play() ЗАВЕРШЁН (процесс игры запущен)")
            _log("=" * 60)

        except Exception as e:
            _log("=" * 60)
            _log("!!! play() УПАЛ С ОШИБКОЙ:", type(e).__name__, "-", e)
            _log("=" * 60)
            _log(traceback.format_exc())
            raise


__all__ = ["MinecraftProvider", "MinecraftVersion", "MinecraftRunner"]