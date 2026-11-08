from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

DEFAULT_PATH = Path(__file__).parent / "portfolio.yaml"


class Holding(BaseModel):
    symbol: str
    name: str
    sector: str
    size: Literal["mega", "large", "mid", "small"]
    yahoo: str = ""

    @model_validator(mode="after")
    def _default_yahoo(self) -> "Holding":
        if not self.yahoo:
            self.yahoo = self.symbol + ".NS"
        return self


def load_portfolio(path: Path | None = None) -> list[Holding]:
    data = yaml.safe_load((path or DEFAULT_PATH).read_text(encoding="utf-8"))
    return [Holding(**h) for h in data["holdings"]]
