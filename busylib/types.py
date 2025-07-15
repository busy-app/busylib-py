import dataclasses


@dataclasses.dataclass(frozen=True)
class ApiResponse:
    """A generic response from the BusyBar API"""

    success: bool
    message: str | None = None
