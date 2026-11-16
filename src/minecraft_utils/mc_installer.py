import os
import json
import shutil
import logging
import subprocess
import zipfile
import tempfile
import xml.etree.ElementTree as ET
from functools import cache

import requests
import minecraft_launcher_lib as mll

from .models import MinecraftVersion, MinecraftProvider, InstallerError

logger = logging.getLogger(__name__)

MIRROR_URL = "https://neoforged.forgecdn.net"
FALLBACK_MIRROR = "https://bmclapi2.bangbang93.com"

_original_request = requests.Session.request
_original_popen = subprocess.Popen
_original_run = subprocess.run


# ---------- Зеркало для API версий NeoForge (без изменений) ----------

def _fetch_neoforge_versions(session, method, original_url, *args, **kwargs):
    api_path = "/api/maven/versions/releases/net/neoforged/neoforge"
    mirror_urls = [
        f"{MIRROR_URL}{api_path}",
        f"{MIRROR_URL}/releases/net/neoforged/neoforge/maven-metadata.xml",
    ]

    for url in mirror_urls:
        try:
            resp = _original_request(session, method, url, *args, **kwargs)
            if resp.status_code != 200:
                continue
            text = resp.text.strip()
            if not text:
                continue
            if text.startswith("<"):
                root = ET.fromstring(text)
                versions = [v.text for v in root.findall(".//version") if v.text]
                if versions:
                    logger.info(f"[NEOFORGE-MIRROR] Получено {len(versions)} версий из XML: {url}")
                    return versions
            else:
                data = resp.json()
                versions = data.get("versions")
                if versions:
                    logger.info(f"[NEOFORGE-MIRROR] Получено {len(versions)} версий из API: {url}")
                    return versions
        except Exception as e:
            logger.warning(f"[NEOFORGE-MIRROR] Ошибка при запросе {url}: {e}")

    bmcl_url = f"{FALLBACK_MIRROR}/maven/releases/net/neoforged/neoforge/maven-metadata.xml"
    try:
        resp = _original_request(session, method, bmcl_url, *args, **kwargs)
        if resp.status_code == 200 and resp.text.strip().startswith("<"):
            root = ET.fromstring(resp.text)
            versions = [v.text for v in root.findall(".//version") if v.text]
            if versions:
                logger.info(f"[NEOFORGE-MIRROR] Получено {len(versions)} версий из BMCLAPI XML")
                return versions
    except Exception as e:
        logger.warning(f"[NEOFORGE-MIRROR] Ошибка BMCLAPI: {e}")

    return None


def _patched_request(self, method, url, *args, **kwargs):
    url_str = str(url)

    if "maven.neoforged.net" in url_str and "/api/maven/versions/" in url_str:
        logger.info(f"[NEOFORGE-MIRROR] Перехвачен запрос версий: {url_str}")
        versions = _fetch_neoforge_versions(self, method, url_str, *args, **kwargs)
        if versions is None:
            logger.error("[NEOFORGE-MIRROR] Не удалось получить список версий ни с одного зеркала")
            versions = []

        fake_resp = requests.Response()
        fake_resp.status_code = 200
        fake_resp._content = json.dumps({"versions": versions}).encode("utf-8")
        fake_resp.headers["Content-Type"] = "application/json"
        fake_resp.url = url_str
        fake_resp.encoding = "utf-8"
        logger.info(f"[NEOFORGE-MIRROR] Возвращаем {len(versions)} версий")
        return fake_resp

    if "maven.neoforged.net" in url_str:
        new_url = url_str.replace("maven.neoforged.net", "neoforged.forgecdn.net", 1)
        logger.info(f"[NEOFORGE-MIRROR] Перенаправление файла: {url_str} -> {new_url}")
        url = new_url

    return _original_request(self, method, url, *args, **kwargs)


# ---------- Модификация JAR-файла инсталлятора NeoForge ----------

def _replace_url_in_jar(jar_path: str, old_domain: str, new_domain: str) -> bool:
    """
    Открывает JAR-файл, находит внутри все текстовые файлы (JSON, properties и т.п.),
    заменяет old_domain на new_domain и перезаписывает JAR.
    Возвращает True, если были произведены замены.
    """
    if not os.path.isfile(jar_path):
        return False

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jar")
    os.close(tmp_fd)

    changed = False
    try:
        with zipfile.ZipFile(jar_path, "r") as zin:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    # Пытаемся декодировать как текст; если не получается — оставляем как есть
                    try:
                        text = data.decode("utf-8")
                        if old_domain in text:
                            new_text = text.replace(old_domain, new_domain)
                            data = new_text.encode("utf-8")
                            changed = True
                            logger.info(f"[JAR-PATCH] Заменено вхождение '{old_domain}' -> '{new_domain}' в {item.filename}")
                    except UnicodeDecodeError:
                        pass
                    zout.writestr(item, data)

        if changed:
            shutil.move(tmp_path, jar_path)
            logger.info(f"[JAR-PATCH] JAR-файл обновлён: {jar_path}")
        else:
            os.remove(tmp_path)
    except Exception as e:
        logger.error(f"[JAR-PATCH] Ошибка при модификации {jar_path}: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False

    return changed


class _PatchedPopen(_original_popen):
    def __init__(self, args, *p_args, **kwargs):
        # args обычно список: [java, -jar, <path_to_installer.jar>, --install-client, ...]
        if isinstance(args, (list, tuple)) and "-jar" in args:
            try:
                jar_index = args.index("-jar") + 1
                if jar_index < len(args):
                    jar_path = args[jar_index]
                    if jar_path.endswith(".jar") and "neoforge" in os.path.basename(jar_path).lower():
                        logger.info(f"[JAR-PATCH] Обнаружен инсталлятор NeoForge: {jar_path}")
                        _replace_url_in_jar(jar_path, "maven.neoforged.net", "neoforged.forgecdn.net")
            except Exception as e:
                logger.warning(f"[JAR-PATCH] Не удалось модифицировать JAR: {e}")

        super().__init__(args, *p_args, **kwargs)


def _patched_run(args, *p_args, **kwargs):
    if isinstance(args, (list, tuple)) and "-jar" in args:
        try:
            jar_index = args.index("-jar") + 1
            if jar_index < len(args):
                jar_path = args[jar_index]
                if jar_path.endswith(".jar") and "neoforge" in os.path.basename(jar_path).lower():
                    _replace_url_in_jar(jar_path, "maven.neoforged.net", "neoforged.forgecdn.net")
        except Exception:
            pass
    return _original_run(args, *p_args, **kwargs)


requests.Session.request = _patched_request
subprocess.Popen = _PatchedPopen
subprocess.run = _patched_run


# ---------- Строгая проверка полноты установки (без изменений) ----------

def _check_version_complete(version_id: str, install_dir: str) -> tuple[bool, list[str]]:
    version_dir = os.path.join(install_dir, "versions", version_id)
    version_json = os.path.join(version_dir, f"{version_id}.json")

    if not os.path.isfile(version_json):
        return False, [version_json]

    try:
        with open(version_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, [f"invalid JSON: {version_json}: {e}"]

    missing: list[str] = []

    for lib in data.get("libraries", []):
        artifact = lib.get("downloads", {}).get("artifact")
        if artifact and "path" in artifact:
            lib_path = os.path.join(install_dir, "libraries", artifact["path"])
            if not os.path.isfile(lib_path):
                missing.append(lib_path)

    version_jar = os.path.join(version_dir, f"{version_id}.jar")
    if not os.path.isfile(version_jar):
        missing.append(version_jar)

    return len(missing) == 0, missing


class MinecraftInstaller:
    @staticmethod
    @cache
    def get_path():
        return mll.utils.get_minecraft_directory().replace("minecraft", "grapegg-mc")

    @staticmethod
    def install_minecraft(
        ver: MinecraftVersion,
        callback_dict: dict,
        java: str | None = None,
    ) -> tuple[InstallerError | None, str | None]:
        if ver.provider != MinecraftProvider.VANILLA:
            mod_loader = mll.mod_loader.get_mod_loader(ver.provider.value)
            if not mod_loader.is_minecraft_version_supported(ver.version):
                return (
                    InstallerError(
                        error=f"This version is not supported by {ver.provider.name}. Please try again later.",
                        level=3,
                    ),
                    None,
                )

            loader_version = mod_loader.get_latest_loader_version(ver.version)
            installed_version_id = mod_loader.get_installed_version(ver.version, loader_version)
            install_dir = (
                MinecraftInstaller.get_path()
                + f"/{"_".join(ver.server_name.capitalize().split())}_{ver.version}_{ver.provider.value}"
            )

            vanilla_json = os.path.join(install_dir, "versions", ver.version, f"{ver.version}.json")
            if not os.path.exists(vanilla_json):
                try:
                    logger.info(f"[MC-INSTALLER] Ставим ванильный {ver.version} в {install_dir}")
                    mll.install.install_minecraft_version(ver.version, install_dir, callback=callback_dict)
                except Exception as _ex:
                    return (
                        InstallerError(error=f"Не удалось установить ванильный Minecraft: {_ex}", level=4),
                        None,
                    )

            version_dir_path = os.path.join(install_dir, "versions", installed_version_id)
            need_reinstall = False

            if os.path.isdir(version_dir_path):
                complete, missing = _check_version_complete(installed_version_id, install_dir)
                if not complete:
                    logger.warning(
                        f"[MC-INSTALLER] Установка {installed_version_id} неполная: "
                        f"отсутствует {len(missing)} файлов. Удаляем и ставим заново."
                    )
                    for m in missing[:15]:
                        logger.warning(f"[MC-INSTALLER]   MISS: {m}")
                    try:
                        shutil.rmtree(version_dir_path, ignore_errors=True)
                    except Exception as e:
                        logger.error(f"[MC-INSTALLER] Не удалось удалить {version_dir_path}: {e}")
                    need_reinstall = True
                else:
                    logger.info(f"[MC-INSTALLER] {installed_version_id} уже установлен полностью, пропускаем")
            else:
                need_reinstall = True

            if need_reinstall:
                try:
                    logger.info(f"[MC-INSTALLER] Ставим {ver.provider.value} {loader_version}...")
                    mod_loader.install(
                        ver.version,
                        install_dir,
                        loader_version=loader_version,
                        callback=callback_dict,
                        java=java,
                    )
                except Exception as _ex:
                    versions_dir = os.path.join(install_dir, "versions")
                    if os.path.isdir(versions_dir):
                        logger.info(f"[MC-INSTALLER] УСТАНОВКА УПАЛА! Содержимое versions/: {os.listdir(versions_dir)}")
                    else:
                        logger.info(f"[MC-INSTALLER] УСТАНОВКА УПАЛА! Папки versions/ нет по пути {versions_dir}")

                    return (
                        InstallerError(
                            error=_ex.__str__() + " Contact admin with screenshot of your error.",
                            level=4,
                        ),
                        None,
                    )

            complete, missing = _check_version_complete(installed_version_id, install_dir)
            if not complete:
                logger.error(
                    f"[MC-INSTALLER] После установки {installed_version_id} всё ещё не хватает "
                    f"{len(missing)} файлов"
                )
                for m in missing[:15]:
                    logger.error(f"[MC-INSTALLER]   MISS: {m}")
                return (
                    InstallerError(
                        error=(
                            f"{ver.provider.name} установился, но {len(missing)} файлов отсутствуют. "
                            "Проверьте лог mc_debug.log."
                        ),
                        level=4,
                    ),
                    None,
                )

            return None, install_dir

        return None, None