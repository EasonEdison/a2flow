"""Offline production-composition and immutable HTTP-contract CI gate.

Only the focused route/composition suite is loaded. Each real assembly factory
uses blocked network/database boundaries; no listener, model or live operation
is started. This is source compatibility evidence, not deployment acceptance.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "services/b-side-api/tests"))
    sys.path.insert(0, str(root / "examples/activity-planning"))
    suite = unittest.defaultTestLoader.loadTestsFromName("test_route_composition")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.wasSuccessful() and result.testsRun >= 5 and not result.skipped
    print(
        json.dumps(
            {
                "result": "PASS" if passed else "FAIL",
                "probe": "python-route-composition",
                "checks": result.testsRun,
                "postgres": False,
            }
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
