from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    """
    Хранить конфигурацию MCP-сервера из окружения и явных override.

    Класс задает единый источник параметров подключения к одному Busy Bar
    и используется как в CLI, так и в точке запуска сервера.
    """

    addr: str = Field(
        default="http://10.0.4.20",
        description="Base URL Busy Bar устройства.",
    )
    token: SecretStr | None = Field(
        default=None,
        description="API token устройства.",
    )
    timeout_seconds: float = Field(
        default=10.0,
        ge=0.1,
        description="Таймаут запросов к устройству в секундах.",
    )
    verify_ssl: bool = Field(
        default=True,
        description="Включить проверку TLS-сертификата.",
    )

    model_config = SettingsConfigDict(
        env_prefix="BUSYLIB_MCP_",
        extra="ignore",
    )

    def safe_dict(self) -> dict[str, str | float | bool | None]:
        """
        Вернуть безопасное представление настроек для логов и диагностики.

        Токен маскируется, чтобы не выводить секрет в stdout/stderr.
        """
        token_value = self.token.get_secret_value() if self.token is not None else None
        masked_token = "***" if token_value else None
        return {
            "addr": self.addr,
            "token": masked_token,
            "timeout_seconds": self.timeout_seconds,
            "verify_ssl": self.verify_ssl,
        }
