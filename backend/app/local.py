"""Single-process, loopback-only application for trying the product locally."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app.db import create_schema
from app.main import app as api_app

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class SinglePageFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and "." not in Path(path).name:
                return await super().get_response("index.html", scope)
            raise


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    yield


app = FastAPI(title="A 股个股研究智能体（本机）", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/api", api_app)
app.mount("/", SinglePageFiles(directory=FRONTEND_DIST, html=True))
