import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEAM_PIPELINE = ROOT / "Pipelineteamfile"
TEAM_DB = TEAM_PIPELINE / "data" / "articles.db"
# A fresh clone reads its own local database. Developers with the established
# analysis corpus can opt into that read source with RADAR_SOURCE_DB; writes
# remain directed to TEAM_DB.
SOURCE_DB = Path(os.getenv(
    "RADAR_SOURCE_DB",
    str(TEAM_DB),
))
EXTENSION_DB = ROOT / "data" / "product.db"
DOCUMENTS = ROOT / "Documents"
TAXONOMY = TEAM_PIPELINE / "opportunity_classifier" / "config" / "taxonomy.json"
# Role mode is a pure view concept with no pipeline involvement, so it lives with
# the app rather than in the classifier config directory.
ROLE_MODES = Path(__file__).resolve().parent / "config" / "role_modes.json"

ORANGE = "#ff7900"
INK = "#090909"
PANEL = "#141414"
PANEL_SOFT = "#1c1c1c"
LINE = "#303030"
TEXT = "#f7f7f4"
MUTED = "#a2a2a0"
