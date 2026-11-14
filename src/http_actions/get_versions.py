#todo: mock data

from .models import ServerData
from minecraft_utils.models import MinecraftProvider

def get_all_versions() -> list[ServerData]:
    return [
        ServerData(
            name="Pokecraft 1.21.1",
            mc_ver='1.21.1',
            provider=MinecraftProvider.QUILT,
            java_ver='21',
            mod_path=''
        ),
        ServerData(
            name="RP 1.20.4",
            mc_ver='1.20.4',
            provider=MinecraftProvider.NEOFORGE,
            java_ver='17',
            mod_path=''
        )
    ]