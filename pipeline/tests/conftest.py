import os
import sys
import tempfile
from pathlib import Path

# Tests write snapshots and reports into a throwaway root, never into the repo.
os.environ["UNCOUNTED_ROOT"] = tempfile.mkdtemp(prefix="uncounted-test-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
