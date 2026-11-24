"""A workflow stand-in for scheduler tests: prints text a GBK console cannot encode.

Run as ``python -m tests.skills.live_trade.stub_workflow ...`` from the repository root. It
exits with the code after ``--exit`` (default 2, a crash), so a schedule can use it to try
``serve`` without data or credentials.
"""

from __future__ import annotations

import sys

if __name__ == "__main__":
    args = sys.argv[1:]
    code = int(args[args.index("--exit") + 1]) if "--exit" in args else 2
    print("目标已推送 ✓", flush=True)
    print(f"策略进程失败 ✗ {' '.join(args[:2])}", file=sys.stderr, flush=True)
    sys.exit(code)
