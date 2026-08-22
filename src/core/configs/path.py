from pathlib import Path
from typing import Final


""" Project Route Definitions """

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

STORAGE_DIR: Final[Path] = PROJECT_ROOT / "storage"
CONFIG_DIR: Final[Path] = STORAGE_DIR / "configs"

CONFIG_DB: Final[Path] = CONFIG_DIR / "Configs.db"
VALUE_DB: Final[Path] = CONFIG_DIR / "ValueData.db"


PUBLIC = PROJECT_ROOT / "public"
FONTS = PUBLIC / "fonts"
ASSETS = PUBLIC / "assets"

TRANSCRIPT_DIR: Final[Path] = (
    PROJECT_ROOT
    / "src"
    / "core"
    / "features"
    / "ticketing"
    / "transcript"
)

TRANSCRIPT_TEMPLATE_DIR: Final[Path] = TRANSCRIPT_DIR / "static"