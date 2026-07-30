# Converters

Media is converted into device-ready formats before upload. Unknown
extensions pass through untouched; known ones must convert successfully or a
`BusyBarConversionError` is raised.

::: busylib.converter
