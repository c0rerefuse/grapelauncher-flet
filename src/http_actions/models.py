from pydantic import BaseModel
from minecraft_utils.models import MinecraftProvider

class ServerData(BaseModel):
    name: str
    mc_ver: str
    provider: MinecraftProvider
    java_ver: str
    mod_path: str