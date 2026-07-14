"""Service configuration via environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SUBFLY_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8765

    # Whisper / faster-whisper
    model_size: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "float16"
    language: str = "en"
    beam_size: int = 5
    vad_filter: bool = True
    word_timestamps: bool = False

    # Audio pipeline
    sample_rate: int = 16000
    chunk_seconds: float = 3.0
    overlap_seconds: float = 0.5
    min_audio_seconds: float = 0.8

    # Path rewriting: Kodi path prefix -> container mount prefix
    # Example: "/media|=/data" maps Kodi /media/Movies/x.mkv -> /data/Movies/x.mkv
    path_maps: str = ""

    # CORS / security
    allow_origins: str = "*"
    api_token: str = ""

    # Model download / cache
    download_root: str = "/models"

    def path_map_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for item in self.path_maps.split(","):
            item = item.strip()
            if not item or "=" not in item:
                continue
            src, dst = item.split("=", 1)
            pairs.append((src.strip(), dst.strip()))
        return pairs


@lru_cache
def get_settings() -> Settings:
    return Settings()
