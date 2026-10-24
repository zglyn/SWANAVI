"""Book the checked-in sample plan with process-local memory and no AWS calls.

Run from the repository root:

    python -m pip install -r booking/orchestrator/requirements.txt
    PYTHONPATH=. python -m booking.orchestrator.demo

Sibling providers are used when they are importable. Otherwise each segment
comes back ``failed`` with ``error`` ``provider_not_installed``. Confirmation
codes are never minted here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from booking.orchestrator.memory import LocalBookingMemory
from booking.orchestrator.service import handle_payload

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_plan.json"


def main() -> int:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = handle_payload(payload, LocalBookingMemory())
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
