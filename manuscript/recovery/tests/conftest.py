import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "manuscript" / "recovery"))
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"))
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-emc-server"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
