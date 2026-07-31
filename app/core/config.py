from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Zentrale Konfiguration, aus ENV/.env geladen.

    Prototyp-Phase: SEED_DEMO_DATA legt Demo-Nutzer an, damit die
    Funktionalität ohne manuelle DB-Vorbereitung bewertet werden kann.
    Muss in echten Einrichtungen zwingend auf false stehen.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    secret_key: str
    field_encryption_key: str
    seed_demo_data: bool = False
    debug: bool = False
    upload_dir: str = "/app/uploads"


settings = Settings()
