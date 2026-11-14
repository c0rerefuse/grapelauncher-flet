import os

import jdk

from .mc_installer import MinecraftInstaller
from .models import MinecraftVersion

class JavaInstaller:
    def install_java(mcv: MinecraftVersion):
        path = MinecraftInstaller.get_path()+f"/java"
        jdk.install(mcv.java_version, jre=True, path=path)