"""Live smoke test: one complete_json per distinct (provider, model) in ROUTES.

Run: uv run python scripts/llm_smoke.py   (exit 1 if any model fails)
"""

import json
import time

from finn import db
from finn.config import ROUTES, get_settings, route_for
from finn.llm import LLMError, LLMRouter

settings = get_settings()
conn = db.connect(settings.llm_cache_path)  # never the serving DB
db.init_db(conn)
router = LLMRouter(conn, settings)

first_task: dict[tuple[str, str], str] = {}
for task in ROUTES:
    first_task.setdefault(route_for(task, settings), task)

failed = 0
nonce = int(time.time())  # a fresh prompt per run, so the response cache can't mask an outage
for (provider, model), task in first_task.items():
    try:
        out = router.complete_json(
            task, "Reply with a JSON object echoing the input.", json.dumps({"ping": nonce})
        )
        print(f"ok    {provider}/{model} ({task}): {json.dumps(out)}")
    except LLMError as e:
        failed += 1
        print(f"FAIL  {provider}/{model} ({task}): {e}")
print(router.stats())
raise SystemExit(1 if failed else 0)
