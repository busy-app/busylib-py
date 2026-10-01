# Managing apps on a bar

A BUSY Bar can run JavaScript applications. Until there is a catalog to pick
them from, getting one onto a bar means building it or finding a release,
making a package the bar will take, and uploading it. The app manager in
[`examples/apps`](https://github.com/busy-app/busylib-py/tree/main/examples/apps)
does those steps for you, in a terminal, on Windows, macOS or Linux.

It is an example, not part of the installed package: it lives in the source
checkout, next to the other examples, and shows how the pieces fit together.

## What it needs

- The source checkout and virtual environment from
  [Step 2 of the README](https://github.com/busy-app/busylib-py#step-2--first-time-setup).
- The `textual` package, which draws the interface.
- A bar whose firmware has JavaScript apps. At the time of writing that is
  development firmware only; on anything older the manager says so rather
  than failing.
- To install **from a release**: nothing else.
- To **build from source**: pnpm and Node.js **before version 26** - the
  engine that runs the apps' tooling does not work on anything newer - and
  whatever else the app's own `package.json` asks for (the BUSY apps ask for
  `>=24 <26`). The manager checks `node --version` first and says so, rather
  than letting a build fail somewhere in its dependencies.

## Running it

```powershell
.\.venv\Scripts\python.exe -m pip install textual
.\.venv\Scripts\python.exe -m examples.apps.main 192.168.1.20
```

```bash
.venv/bin/python -m pip install textual
.venv/bin/python -m examples.apps.main 192.168.1.20
```

Without an address it looks for a bar on the network, as the other examples
do. `--token` gives the access key when the bar wants one, and `--offline`
starts without a bar, for managing sources and programs on their own.

The main screen lists everything that can be started: the applications on the
bar, found by asking it, and the programs you added from this computer. The
panel on the right is the card of whatever is highlighted.

| Key | Does |
| --- | --- |
| `Enter` | Launch the app on the bar, or run the program here |
| `i` | Install an app from a source |
| `x` | Quit the app running on the bar, or stop the highlighted program |
| `d` | Remove the app from the bar, or forget the program |
| `e` / `m` | Add / modify a program from this computer |
| `b` | Dashboard: the same things as cards |
| `r` | Refresh |
| `q` | Quit the manager |

## Sources

A source is a GitHub repository. `i` opens the list of them; `a` adds one.
Adding a source asks GitHub straight away, so a typo in the name is a message
in the form and not a puzzle later.

A source installs in one of two ways:

- **A release.** The package a maintainer attached to a GitHub release. Pick
  the version from the list, newest first; pre-releases are marked. If a
  release carries several files, the *release file* pattern (`*.tgz` by
  default, comma-separated for more) says which one is the package.
- **The source, built here.** The repository at a branch or tag, built with
  `pnpm` (or `npm`) and packaged. For trying something nobody has released.

For a repository that holds several apps, name the *folder*. If the app's
manifest is not in `src/appmeta/manifest.json` or `appmeta/manifest.json`,
give its path.

Installing is two steps, and the second asks first. The package is checked and
handed to the bar, which unpacks it and says what it would replace:

```
downloading demo.tgz
checking the package
Demo 1.2.0 (demo.app), 4 KiB
handing it to the bar
Replace Demo 1.0.0 with 1.2.0. Go ahead?
```

Nothing on the bar has changed at that point. Cancelling leaves the bar as it
was, apart from the package it keeps until another replaces it.

## What a package is

The bar's installer unpacks the archive and looks at its **first level** for a
folder that loads as an application, taking the first that does. So a package
is a `.tgz` holding exactly one folder, named for the app:

```
demo.app/
  appmeta/manifest.json
  scripts/main.js
  resources/...
```

Packages arrive in whatever layout their author liked, so the manager reads
each one without unpacking it to disk, checks every name, and writes it again
in this layout: one folder, the same bytes for the same input, without the
`._*` and `.DS_Store` files an operating system leaves in folders. It refuses
anything with a link, a path that leaves its folder, a missing or unreadable
manifest, an id the bar would not accept, or more than one application.

## Programs from this computer

Press `e` to add something that is not on the bar but belongs with it: a script
that draws on the display, a bridge to a service you use. It needs a name, the
folder to run in, and the command that starts it. It then sits in the list
beside the bar's own apps, and on the dashboard.

`Enter` runs it, detached, with its output in a log file; `x` stops it. The
command is run by your shell, as you would type it, and is shown on its card
before you run it. Forgetting a program removes the entry and nothing else.

## Where things are kept

Sources and programs are one JSON file in the place your system keeps such
things (`--config` points elsewhere):

| System | Folder |
| --- | --- |
| Windows | `%APPDATA%\busy-apps` |
| macOS | `~/Library/Application Support/busy-apps` |
| Linux | `$XDG_CONFIG_HOME/busy-apps` or `~/.config/busy-apps` |

Next to it are `manager.log` and a `logs` folder with one file per program.
A file that cannot be read is moved aside as `apps.json.bad` rather than
overwritten.

## From your own code

The manager uses the same client calls you can. Installing is two of them, and
the bar's answer to the first is what lets you show the difference before the
second:

```python
from busylib import BusyBar

with BusyBar("192.168.1.20") as bar:
    staged = bar.apps_stage(open("demo.tgz", "rb").read())
    if staged.installed is not None:
        print(f"replacing {staged.installed.version} with {staged.staged.version}")
    bar.apps_install(staged.install_key)

    bar.apps_launch(staged.staged.id)
```

`apps_list`, `apps_launch`, `apps_quit` and `apps_delete` do what they say;
`apps_settings`, `apps_settings_set` and `apps_settings_reset` read and write an
app's settings as one document. They are marked experimental: no released
firmware serves them yet, and `method_compatibility("apps_stage")` says so.
These endpoints answer on the local network only.

## Limits

- Public repositories only. Anonymous GitHub requests are limited to sixty an
  hour; set `GITHUB_TOKEN` to raise it. The token goes to GitHub's API and
  nowhere else.
- One bar at a time.
- The bar has no call that says which app is running, so `x` quits whichever
  one is.
