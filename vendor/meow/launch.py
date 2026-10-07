"""Official source and portable packages use the same managed launcher."""
from pathlib import Path
import sys

if sys.version_info < (3, 11):
    raise SystemExit('Python 3.11+ required / 需要 Python 3.11 或更新版本')

from gpt56_vnext.managed_launcher import launch

if __name__ == '__main__':
    raise SystemExit(launch(Path(__file__).resolve().parent))
