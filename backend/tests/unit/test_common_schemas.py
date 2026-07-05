from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.common import ErrorResponse, PageParams, PageResponse, SuccessResponse


def test_page_params_defaults_and_offset() -> None:
    params = PageParams()

    assert params.page == 1
    assert params.page_size == 20
    assert params.offset == 0


def test_page_params_custom_offset() -> None:
    params = PageParams(page=3, page_size=50)

    assert params.offset == 100


@pytest.mark.parametrize(
    "payload",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 201},
    ],
)
def test_page_params_rejects_invalid_bounds(payload: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        PageParams(**payload)


def test_page_response_serializes_items() -> None:
    response = PageResponse[dict[str, int]](
        total=2,
        page=1,
        page_size=20,
        items=[{"id": 1}, {"id": 2}],
    )

    assert response.model_dump() == {
        "total": 2,
        "page": 1,
        "page_size": 20,
        "items": [{"id": 1}, {"id": 2}],
    }


def test_success_and_error_response_defaults() -> None:
    assert SuccessResponse().model_dump() == {"status": 0, "msg": "ok", "data": None}
    assert ErrorResponse(status=404, msg="not found").model_dump() == {
        "status": 404,
        "msg": "not found",
        "detail": None,
    }
