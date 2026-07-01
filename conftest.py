"""
Pytest bootstrap. Living at the repo root, this file makes pytest add the
project root to sys.path, so tests can `import sentiment_processor`,
`from utils.date_utils import ...`, etc. without setting PYTHONPATH manually.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
