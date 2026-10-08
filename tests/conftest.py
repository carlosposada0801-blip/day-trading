import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DEMO_MODE", "1")
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("APP_PASSWORD", "test-pass")
os.environ.setdefault("ALERTS_ENABLED", "0")
