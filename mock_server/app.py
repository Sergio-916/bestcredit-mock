from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .core.config import Settings
from .providers.kommo.data import ApiError
from .providers.kommo.router import create_router as kommo_router


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="BestCredit Integration Mocks", version="0.1.0")

    @app.exception_handler(ApiError)
    async def kommo_error(request: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(
            {"title": "Kommo mock error", "status": error.status, "detail": error.detail},
            status_code=error.status,
            media_type="application/problem+json",
        )

    @app.get("/health", tags=["Platform"])
    def health() -> dict[str, str | list[str]]:
        return {"status": "ok", "providers": ["kommo"]}

    app.include_router(kommo_router(settings or Settings.from_env()))
    return app
