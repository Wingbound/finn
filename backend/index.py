"""Vercel entrypoint: the FastAPI preset serves the `app` it finds here."""

from finn.api.main import app

__all__ = ["app"]
