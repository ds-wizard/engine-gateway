import pydantic

from .config import AppConfig


class EngineInfo(pydantic.BaseModel):
    version: str
    built_at: str | None


class GatewayInfo(pydantic.BaseModel):
    title: str
    version: str
    engine_gateway: EngineInfo
    mounts: list[AppConfig] = pydantic.Field(default_factory=list)
    packages: list[str] = pydantic.Field(default_factory=list)
