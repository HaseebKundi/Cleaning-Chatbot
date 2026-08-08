"""
Env-based settings. Same pattern as the original Support Agent project:
everything client-specific (branding, notification channel, DB) is an env var,
so the same codebase serves any cleaning-business client without code edits.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM ---
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # --- Database ---
    # SQLite for local dev. Swap for a Postgres URL in production (see spec section 12).
    DATABASE_URL: str = "sqlite:///./cleaning_chatbot.db"

    # --- Branding (per client) ---
    BUSINESS_NAME: str = "Sparkle Clean Co."
    BUSINESS_TIMEZONE: str = "America/New_York"

    # --- CORS ---
    # Comma-separated list. Lock this to the client's real domain before going live.
    ALLOWED_ORIGINS: str = "*"

    # --- Notifications (app/notify.py) ---
    # Any of these can be left blank; notify.py degrades gracefully and logs instead.
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    OWNER_PHONE_NUMBER: str = ""  # E.164 format, e.g. +15551234567

    SLACK_WEBHOOK_URL: str = ""

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    OWNER_EMAIL: str = ""

    # --- Agent behavior ---
    CONFIDENCE_THRESHOLD: float = 0.55  # below this, ask a clarifying question instead of guessing

    @property
    def cors_origins(self) -> list[str]:
        if self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
