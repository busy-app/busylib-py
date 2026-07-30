# Exceptions

Every failure is surfaced as a `BusyBarError` subclass, so callers can catch
the domain error rather than transport-specific exceptions.

::: busylib.exceptions
