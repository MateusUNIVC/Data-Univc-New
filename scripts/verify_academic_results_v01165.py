from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_academic_results_v01165")
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
print("OK v0.11.6.5: leitura por aluno reconciliada e filtros rápidos validados.")
