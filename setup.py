"""Supply derived metadata through setuptools' normal PEP 517 build hooks."""
from pathlib import Path
import runpy

from setuptools import setup

root = Path(__file__).resolve().parent
metadata = runpy.run_path(str(root / "build_readme.py"))["build_metadata"](root)
setup(**metadata)
