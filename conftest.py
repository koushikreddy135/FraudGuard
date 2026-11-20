# Makes the project folder importable for pytest (so tests can `import policy`, `import serve`).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
