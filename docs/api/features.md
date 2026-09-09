# Features

Higher-level helpers built on top of the raw client: notification layout for
the front panel, timer state and control, a device snapshot for dashboards, a
store that applies streamed protobuf state updates, and asset syncing.

For notifications, start with the
[Sending notifications](../guides/notifications.md) guide - it covers the
built-in templates and how to write your own. For timers, see
[Working with timers](../guides/timers.md), which explains why a snapshot has
to be advanced before it means anything.

::: busylib.features

## Timers

The control helpers are reached through the module - `timer.start(bar)` - so
that names like `start` and `stop` stay unambiguous at the call site.

::: busylib.features.timer
