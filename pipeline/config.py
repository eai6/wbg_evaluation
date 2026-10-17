"""Pipeline configuration. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("SCORECARD_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DB_PATH = Path(os.getenv("SCORECARD_DB_PATH", DATA_DIR / "scorecard.duckdb"))

SCORECARD_SITE = "https://scorecard.worldbank.org/"
SCORECARD_API = "https://ext.api.worldbank.org/api/Scorecard/"
SCORECARD_CMS = "https://scorecardcmsapi.worldbank.org/scorecard/cache/"
DATA360_API = "https://data360api.worldbank.org/data360/"
PROJECTS_API = "https://search.worldbank.org/api/v2/projects"

# Snapshots published on the Scorecard (FY). The latest is what the live site shows.
SNAPSHOTS = [int(s) for s in os.getenv("SCORECARD_SNAPSHOTS", "2024,2025,2026").split(",")]

# Aggregate areas queried in addition to every country.
REGIONS = ["ACW", "AFE", "AFW", "EAP", "ECA", "LCR", "MENAAP", "SAR"]
INSTITUTIONS = ["WB", "IFC", "MIGA"]

# Data360 (WDI) context series pulled for every country.
DATA360_INDICATORS = {
    "population": "WB_WDI_SP_POP_TOTL",
    "gdp_per_capita": "WB_WDI_NY_GDP_PCAP_CD",
}

HTTP_TIMEOUT = int(os.getenv("SCORECARD_HTTP_TIMEOUT", "90"))
HTTP_RETRIES = int(os.getenv("SCORECARD_HTTP_RETRIES", "3"))
MAX_WORKERS = int(os.getenv("SCORECARD_MAX_WORKERS", "10"))
USER_AGENT = "scorecard-explorer-pipeline/1.0 (+assessment prototype)"
