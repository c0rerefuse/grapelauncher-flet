from pydantic import BaseModel, Field
from enum import Enum

class MinecraftProvider(Enum):
    VANILLA = "vanilla"
    FABRIC = "fabric"
    QUILT = "quilt"
    FORGE = "forge"
    NEOFORGE = "neoforge"

class MinecraftVersion(BaseModel):
    version: str = Field(min_length=1)
    provider: MinecraftProvider
    server_name: str = Field(min_length=1)
    java_version: str = Field(min_length=1)

class InstallerError(BaseModel):
    error: str
    level: int #1 - Info, 2 - Warning, 3 - Error, 4 - Critical