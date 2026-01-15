#!/usr/bin/env python3

import argparse
import inspect
import sys

from busylib.client.usb import UsbController
from busylib.exceptions import BusyBarUsbError


def get_available_commands(controller):
    """
    Return a mapping of command name to callable and help text.

    This inspects public methods on the controller instance.
    """
    commands = {}
    for name in dir(controller):
        if name.startswith("_"):
            continue
        attr = getattr(controller, name)
        if not inspect.ismethod(attr):
            continue
        # Skip utility methods if needed, but we expose most public ones
        commands[name] = (attr, attr.__doc__ or "No description.")
    return commands


def main():
    """
    Run the Busy Bar telnet CLI wrapper.

    The command list is discovered dynamically from the controller instance.
    """
    parser = argparse.ArgumentParser(description="Busy Bar USB Control CLI")
    parser.add_argument(
        "-H",
        "--host",
        default="10.0.4.20",
        help="Telnet host for the Busy Bar CLI",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=23,
        help="Telnet port for the Busy Bar CLI",
    )

    # Introspection-based command structure
    parser.add_argument("command", nargs="?", help="Command to execute")
    parser.add_argument(
        "args", nargs=argparse.REMAINDER, help="Arguments for the command"
    )

    args = parser.parse_args()

    # Initialize controller
    try:
        controller = UsbController(host=args.host, port=args.port)
    except Exception as e:
        print(f"Initialization Error: {e}")
        sys.exit(1)

    available = get_available_commands(controller)

    # Show help if no command or help requested without args
    if not args.command or (args.command in ("help", "--help", "-h") and not args.args):
        print("Available commands:")
        print(f"  {'Command':<20} Description")
        print(f"  {'-' * 20} -----------")
        for name, (_, doc) in sorted(available.items()):
            # Use first line of docstring
            first_line = (doc or "").split("\n")[0]
            print(f"  {name:<20} {first_line}")
        return

    cmd_name = args.command
    if cmd_name not in available:
        print(f"Error: Unknown command '{cmd_name}'")
        sys.exit(1)

    method, _ = available[cmd_name]

    try:
        # Check connection before executing if the method is likely to need it
        # Most methods do, but finding the device is done in init.
        # We rely on the method to raise BusyBarUsbError if needed.

        # args.args is a list of strings
        res = method(*args.args)
        if res is not None:
            print(res)

    except BusyBarUsbError as e:
        print(f"USB Error: {e}")
        sys.exit(1)
    except TypeError as e:
        print(f"Argument Error: {e} (Check command usage)")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
