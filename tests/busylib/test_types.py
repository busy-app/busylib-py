from __future__ import annotations

import pytest
from pydantic import BaseModel as PydanticBaseModel

from busylib import exceptions, types


def test_model_validate_forwards_only_what_was_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Unset options never reach pydantic.

    `by_alias`/`by_name` exist only from pydantic 2.11 and `extra` from 2.12,
    so forwarding them unconditionally raised `TypeError` on every call for
    anyone on an older pydantic than the one this package develops against -
    which the declared version floor still permits.
    """
    seen: dict[str, object] = {}
    original = PydanticBaseModel.model_validate.__func__  # type: ignore[attr-defined]

    def spy(cls: type, obj: object, **kwargs: object) -> object:
        seen.update(kwargs)
        return original(cls, obj, **kwargs)

    monkeypatch.setattr(PydanticBaseModel, "model_validate", classmethod(spy))

    types.VersionInfo.model_validate({"api_semver": "25.0.0"})

    assert seen == {}


def test_model_validate_still_passes_options_that_are_set() -> None:
    """
    An option the caller sets is honoured rather than dropped.
    """
    info = types.VersionInfo.model_validate({"api_semver": "25.0.0"}, strict=True)

    assert info.api_semver == "25.0.0"


def test_validation_failures_become_domain_errors() -> None:
    """
    A schema mismatch is reported as a busylib error, not a pydantic one.
    """
    with pytest.raises(exceptions.BusyBarResponseValidationError):
        types.VersionInfo.model_validate({"api_semver": []})
