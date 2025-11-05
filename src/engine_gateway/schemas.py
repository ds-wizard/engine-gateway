import pydantic

from .config import AppConfig


class GatewayInfo(pydantic.BaseModel):
    version: str
    built_at: str | None
    mounts: list[AppConfig] = pydantic.Field(default_factory=list)
    packages: list[str] = pydantic.Field(default_factory=list)
