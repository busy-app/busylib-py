import pytest

from busylib import versioning
from busylib.exceptions import BusyBarAPIVersionError


def test_compatible_equal_versions():
    versioning.ensure_compatible(library_version="0.1.0", device_version="0.1.0")


def test_device_newer_minor_is_allowed():
    versioning.ensure_compatible(library_version="0.1.0", device_version="0.2.0")


def test_device_major_behind_triggers_error():
    with pytest.raises(BusyBarAPIVersionError) as exc:
        versioning.ensure_compatible(library_version="1.0.0", device_version="0.9.0")
    assert "update firmware" in str(exc.value)


def test_library_outdated_for_device_major():
    with pytest.raises(BusyBarAPIVersionError) as exc:
        versioning.ensure_compatible(library_version="0.9.0", device_version="1.0.0")
    assert "update Busy Lib" in str(exc.value)


def test_minor_mismatch_requires_device_update():
    with pytest.raises(BusyBarAPIVersionError) as exc:
        versioning.ensure_compatible(library_version="0.2.0", device_version="0.1.0")
    assert "update firmware" in str(exc.value)


def test_invalid_version_format_raises_value_error():
    with pytest.raises(ValueError):
        versioning.ensure_compatible(library_version="invalid", device_version="0.1.0")
