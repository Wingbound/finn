"""Live smoke test: one complete_json per provider. Run: uv run python scripts/llm_smoke.py"""

import json

from finn import db
from finn.config import get_settings
from finn.llm import LLMRouter

settings = get_settings()
conn = db.connect(settings.llm_cache_path)  # never the serving DB
db.init_db(conn)
router = LLMRouter(conn, settings)
for task in ("classify", "extract_pdf"):  # groq, gemini
    out = router.complete_json(task, "Reply with a JSON object echoing the input.", '{"ping":1}')
    print(task, json.dumps(out))
print(router.stats())
