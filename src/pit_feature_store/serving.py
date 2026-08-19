from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request
from redis import Redis

from .catalog import CATALOG_PATH
from .online_engine import (
    compute_features,
    get_virtual_now_epoch,
)


DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def _clock_epoch(redis_client: Any) -> float:
    try:
        epoch = get_virtual_now_epoch(redis_client)
    except ValueError as error:
        raise HTTPException(
            status_code=503,
            detail="Online feature store virtual clock is invalid.",
        ) from error

    if epoch is None:
        raise HTTPException(
            status_code=503,
            detail="Online feature store virtual clock is not ready.",
        )
    return epoch


def create_app(
    redis_client: Any | None = None,
    catalog_path: Path = CATALOG_PATH,
) -> FastAPI:
    application = FastAPI(title="Point-in-Time Feature Store")
    application.state.redis_client = (
        redis_client
        if redis_client is not None
        else Redis.from_url(
            os.environ.get("REDIS_URL", DEFAULT_REDIS_URL),
            decode_responses=True,
        )
    )
    application.state.catalog_path = Path(catalog_path)

    @application.get("/features/{uid}")
    def get_features(
        uid: str,
        request: Request,
        as_of_epoch: Annotated[
            float | None,
            Query(allow_inf_nan=False),
        ] = None,
    ) -> dict[str, object]:
        client = request.app.state.redis_client
        cutoff_epoch = (
            as_of_epoch
            if as_of_epoch is not None
            else _clock_epoch(client)
        )
        features = compute_features(
            client,
            uid,
            cutoff_epoch,
            catalog_path=request.app.state.catalog_path,
        )
        return {
            "uid": uid,
            "as_of_epoch": cutoff_epoch,
            **features,
        }

    return application


app = create_app()
