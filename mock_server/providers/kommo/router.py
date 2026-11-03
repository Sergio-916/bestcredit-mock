import hmac
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import JsonValue, ValidationError
from starlette.concurrency import run_in_threadpool

from ...core.config import Settings
from ...core.storage import JsonStore
from .data import JSON_ADAPTER, ApiError, State, parse_state, seed
from .service import KommoService


def create_router(settings: Settings) -> APIRouter:
    if not settings.kommo_token:
        raise ValueError("KOMMO_MOCK_TOKEN must not be empty")
    store = JsonStore[State](
        settings.data_dir / "kommo.sqlite3",
        lambda: seed(int(time.time())),
        lambda raw: parse_state(JSON_ADAPTER.validate_json(raw)),
    )

    def authenticate(request: Request) -> None:
        supplied = request.headers.get("authorization", "").encode()
        if not hmac.compare_digest(supplied, f"Bearer {settings.kommo_token}".encode()):
            raise ApiError(401, "Invalid local Kommo token")

    router = APIRouter(tags=["Kommo"], dependencies=[Depends(authenticate)])

    async def read_json(request: Request) -> JsonValue:
        try:
            return JSON_ADAPTER.validate_json(await request.body())
        except ValidationError:
            raise ApiError(400, "Invalid JSON body") from None

    @router.get("/_mock/kommo/state")
    def export_state() -> JSONResponse:
        with store.transaction() as state:
            return JSONResponse(state)

    @router.post("/_mock/kommo/reset")
    def reset() -> dict[str, str]:
        with store.transaction() as state:
            state.clear()
            state.update(seed(int(time.time())))
        return {"status": "reset"}

    @router.put("/_mock/kommo/state")
    async def import_state(request: Request) -> dict[str, str]:
        replacement = parse_state(await read_json(request))

        def replace() -> None:
            # Validate before replacing the persisted state.
            validator = KommoService(replacement, str(request.base_url), request.query_params)
            for kind in ("leads", "tasks", "notes"):
                for item in replacement[kind]:
                    validator.validate(kind, item, imported=True)
            with store.transaction() as state:
                state.clear()
                state.update(replacement)

        await run_in_threadpool(replace)
        return {"status": "imported"}

    @router.api_route(
        "/api/v4/{path:path}",
        methods=["GET", "POST", "PATCH"],
        description="Kommo API subset; see docs/kommo-api.md for supported paths.",
    )
    async def dispatch(path: str, request: Request) -> Response:
        body = await read_json(request) if request.method in ("POST", "PATCH") else None

        def execute() -> JsonValue:
            with store.transaction() as state:
                return KommoService(state, str(request.base_url), request.query_params).handle(
                    request.method, path, body
                )

        result = await run_in_threadpool(execute)
        if result is None:
            return Response(status_code=204)
        return JSONResponse(result, media_type="application/hal+json")

    return router
