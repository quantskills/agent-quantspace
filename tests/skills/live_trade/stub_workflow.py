"""A workflow stand-in for scheduler tests: prints text a GBK console cannot encode.

Run as ``python -m tests.skills.live_trade.stub_workflow ...`` from the repository root. It
exits with the code after ``--exit`` (default 2, a crash), after sleeping the seconds after
``--sleep`` (default 0), so a schedule can use it to try ``serve`` without data or credentials.
With ``--spawn PATH`` it first starts a child, as a workflow starts a PandaAI CLI call, that
appends to PATH every 0.1 s for up to a minute: PATH stops growing once that child is dead.
"""

from __future__ import annotations

import subprocess
import sys
import time

HEARTBEAT = (
    "import sys, time\n"
    "for _ in range(600):\n"
    "    open(sys.argv[1], 'a').write('.')\n"
    "    time.sleep(0.1)\n"
)

if __name__ == "__main__":
    args = sys.argv[1:]
    code = int(args[args.index("--exit") + 1]) if "--exit" in args else 2
    if "--spawn" in args:
        beat = [sys.executable, "-c", HEARTBEAT, args[args.index("--spawn") + 1]]
        subprocess.Popen(beat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(float(args[args.index("--sleep") + 1]) if "--sleep" in args else 0)
    print("目标已推送 ✓", flush=True)
    print(f"策略进程失败 ✗ {' '.join(args[:2])}", file=sys.stderr, flush=True)
    sys.exit(code)
