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

    # Virenprüfung hochgeladener Dateien über ClamAV (siehe
    # app/core/virenscan.py). Leerer Host = Prüfung aus (Prototyp-Standard,
    # als offene Lücke dokumentiert). Sobald ein Host gesetzt ist, ist die
    # Prüfung verbindlich: ein nicht erreichbarer Scanner führt dann zur
    # Ablehnung des Uploads, nicht zum stillen Überspringen.
    clamav_host: str | None = None
    clamav_port: int = 3310
    clamav_timeout_sekunden: float = 30.0

    # Session-Cookie nur über HTTPS senden (Secure-Flag) - erst auf true
    # setzen, wenn ein Reverse-Proxy davor TLS terminiert (siehe
    # caddy/Caddyfile.domain-example), sonst verwirft der Browser das
    # Login-Cookie über HTTP stillschweigend und niemand kann sich
    # einloggen. Bewusst derselbe Name wie im Schwestermodul Scandy-Lite.
    session_cookie_secure: bool = False

    # Optional: legt beim Start einen ersten Einrichtungs-Admin an, falls noch
    # keiner mit dieser E-Mail existiert (siehe app/core/seed.py:seed_admin) -
    # für Produktiv-Deployments ohne SEED_DEMO_DATA. Nach dem ersten
    # erfolgreichen Login idealerweise aus der .env entfernen.
    admin_email: str | None = None
    admin_password: str | None = None

    # Optional: Single Sign-On über einen OIDC-Provider (z.B. Authentik) -
    # siehe app/core/oidc.py. Nur aktiv, wenn alle drei Werte gesetzt sind;
    # ohne sie verhält sich die App exakt wie ohne SSO (lokales Login bleibt
    # immer verfügbar). Bewusst dieselben Variablennamen wie im
    # Schwestermodul Scandy-Lite, damit beide Apps gegen denselben Provider
    # konfiguriert werden können.
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_provider_name: str = "SSO"

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret)


settings = Settings()
