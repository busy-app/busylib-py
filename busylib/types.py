from dataclasses import dataclass
from typing import Optional


@dataclass
class ApiResponse:
    """A generic response from the BusyBar API."""

    success: bool
    message: Optional[str] = None
