import os
from functools import cache

import minecraft_launcher_lib as mll

from .models import MinecraftVersion, MinecraftProvider, InstallerError


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
                    print(f"[MC-INSTALLER] Ставим ванильный {ver.version} в {install_dir}")
                    mll.install.install_minecraft_version(ver.version, install_dir, callback=callback_dict)
                except Exception as _ex:
                    return (
                        InstallerError(error=f"Не удалось установить ванильный Minecraft: {_ex}", level=4),
                        None,
                    )
            if not mll.utils.is_version_valid(installed_version_id, install_dir):
                try:
                    print(f"[MC-INSTALLER] Ставим {ver.provider.value} {loader_version}...")
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
                        print(f"[MC-INSTALLER] УСТАНОВКА УПАЛА! Содержимое versions/: {os.listdir(versions_dir)}")
                    else:
                        print(f"[MC-INSTALLER] УСТАНОВКА УПАЛА! Папки versions/ нет по пути {versions_dir}")

                    return (
                        InstallerError(
                            error=_ex.__str__() + " Contact admin with screenshot of your error.",
                            level=4,
                        ),
                        None,
                    )
            if not mll.utils.is_version_valid(installed_version_id, install_dir):
                 return (
                        InstallerError(
                            error=f"Quilt установился, но версия {installed_version_id} не найдена.",
                            level=4,
                        ),
                        None,
                    )

            return None, install_dir

        return None, None