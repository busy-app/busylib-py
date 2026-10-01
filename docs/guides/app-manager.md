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
| `u` | Update a program installed from a catalog |
| `c` | Fill in the settings a catalog program declares |
| `o` | Open a program's page |
| `b` | Dashboard: the same things as cards |
| `r` | Refresh |
| `q` | Quit the manager |

## When the bar goes away

A manager that stays open will see the bar go and come back: it restarts after a
firmware update, its network drops, a cable moves. A list that quietly goes
stale is worse than one that says it has lost the bar, so the manager keeps a
connection and reports it:

- the **title bar** always shows the state - `connected, API 27.9.0`,
  `connection lost - retrying`, or `not reachable - retrying`;
- a **toast** appears when the connection is lost and when it returns, with how
  long it was gone; a bar that was never reachable gets one error, not one per
  retry;
- when it **returns**, the list is read again, since a restarted bar may hold
  different apps, and if its API version changed the toast says so - which is how
  a firmware update shows up from here.

The connection is a WebSocket to the bar's status stream, which closes the
moment the bar reboots or its network goes, so the loss is seen at once; a bar
that vanishes without a word is caught by the socket's own keepalive within
about forty seconds. A closed socket is checked against a fresh question before
it is called a loss, and if the bar answers but the socket cannot be held (a
firmware without it, a proxy that does not pass sockets) the manager quietly
asks every few seconds instead. Retries wait 1, 2, 4, 8 and then 15 seconds.

## A bar behind a tunnel

A bar you cannot reach directly - on a Raspberry Pi's USB network, say - can be
forwarded to a local port and given to the manager as an address:

```bash
ssh -N -L 127.0.0.1:8080:10.0.4.20:80 -J jump.example.com user@pi.local
.venv/bin/python -m examples.apps.main 127.0.0.1:8080
```

An address is needed because discovery does not cross a tunnel. Pick a local
port the browser will accept if you also want the bar's own web interface there:
Chrome, Edge and the Claude Code preview refuse a handful of ports outright -
`10080` among them - so a forward that answers `curl` can still be a blank page
in a browser. `8080`, `8000` and `8888` are fine. A bar reached this way sees the
requests arrive over USB, which is why it asks for no access key.

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
before you run it. Two words in it are filled in when it runs: `{host}` is the
bar the manager is connected to (or `10.0.4.20`, the address of a bar over USB,
when there is none), and `{python}` is the Python that is running the manager.
A program added once therefore follows whichever bar you use it with. An
*Environment* field takes `KEY=value` pairs to set when it runs.

Forgetting a program removes the entry and nothing else.

## Catalogs of programs

Most programs for the bar are not yet anywhere you can browse from the bar. The
[community catalog](https://maxswinkels.github.io/busybar-apps/) (an unofficial
project, `maxswinkels/busybar-apps`) is a repository of folders, one program
each, with a card for every one - name, author, tags, a line about it - and a
command to run it. The manager reads that layout, so a catalog is one more kind
of source:

1. `i`, then `p`, and give the repository (`owner/name`, and a branch if it is
   not `main`). It is read straight away, so a typo is a message in the form.
2. `Enter` on it opens the programs. Type to narrow them by name, tag or
   author; the arrows move through the list while you type; `Enter` takes the
   highlighted one.
3. The manager says what it is about to do before it does it:

```
Install Magic 8-Ball (3 file(s), 27 KiB) in ~/.config/busy-apps/programs/magic-8-ball.
It needs the packages websockets>=15.0. It runs on this computer with your
permissions, so install only what you trust. Go ahead?
```

That last sentence is the point: a program from a catalog is code that runs on
your computer, and the question is not skipped.

What an install does:

- fetches the program's files at one commit and checks every file against the
  sha the listing gave it, so what lands is what was listed;
- builds the new folder beside the old and swaps them, so an install that fails
  halfway leaves the old program working;
- if there is a `requirements.txt`, gives the program an environment of its own
  and installs into it, so its packages touch nothing else on the computer;
- adds it to the list, with `{python} app.py --host {host}` as its command.

A program that has an `.env.example` declares the variables it reads. `c` shows
one field per variable - with the example as a hint, never as a value, and
anything that looks like a key or a token hidden as you type - and saves what
you fill in. The card lists which are set, and never what they are.

The catalog is asked again on every start, cheaply: GitHub answers "unchanged"
to a request that carries the previous answer's tag, and that does not count
against its hourly limit. A program whose own files differ from the catalog's
shows `update` in the list; `u` updates it, asking first, and keeps the command
and settings you changed. A program is not out of date because a neighbour in
the same catalog was edited. `d` on a program installed from a catalog deletes
what it installed and its environment, and nothing it did not install.

This follows the layout of the community catalog and borrows ideas from its own
manager, [busybar-manager](https://github.com/maxswinkels/busybar-manager)
(MIT): update detection by the sha of each file, conditional requests, install
records, per-program environments and the `.env.example` convention. The
manager here is a terminal example and does none of the rest of what that one
does - schedules, autostart, a web dashboard, a proxy for the bar.

## Where things are kept

Sources and programs are one JSON file in the place your system keeps such
things (`--config` points elsewhere):

| System | Folder |
| --- | --- |
| Windows | `%APPDATA%\busy-apps` |
| macOS | `~/Library/Application Support/busy-apps` |
| Linux | `$XDG_CONFIG_HOME/busy-apps` or `~/.config/busy-apps` |

Next to it are `manager.log`, `http-cache.json` (what GitHub answered, kept so
the next start is cheap), `programs/` with the installed programs and their
environments, and a `logs` folder with one file per program.
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
- Programs from a catalog take only `--host`, so they cannot present a bar's
  access key. The firmware enforces the key on connections over Wi-Fi, so such a
  program works over USB or against a bar with no key set, and gets a 403 from
  one that has.
- One bar at a time.
- The bar has no call that says which app is running, so `x` quits whichever
  one is.
