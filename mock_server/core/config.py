import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    kommo_token: str = "local-kommo-token"

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parents[2]
        directory = Path(os.environ.get("MOCK_DATA_DIR", "data"))
        return cls(
            directory if directory.is_absolute() else root / directory,
            os.environ.get("KOMMO_MOCK_TOKEN", "local-kommo-token"),
        )
