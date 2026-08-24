from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEAM_PIPELINE = ROOT / "Pipelineteamfile"
TEAM_DB = TEAM_PIPELINE / "data" / "articles.db"
EXTENSION_DB = ROOT / "data" / "product.db"
DOCUMENTS = ROOT / "Documents"
TAXONOMY = TEAM_PIPELINE / "opportunity_classifier" / "config" / "taxonomy.json"

ORANGE = "#ff7900"
INK = "#090909"
PANEL = "#141414"
PANEL_SOFT = "#1c1c1c"
LINE = "#303030"
TEXT = "#f7f7f4"
MUTED = "#a2a2a0"
