#!/usr/bin/env python

import asyncio
from busylib import BusyBarDevices
from busylib.exceptions import BusyBarError

async def main() -> None:
    device = (await BusyBarDevices.discover())[0]

    usb_client = device.to_async_client("over_usb")
    if not usb_client: raise Exception

    await usb_client.tokens_delete_all()
    print("After delete all:", await usb_client.tokens_list())

    await usb_client.access_set(mode="key", key="1234")

    tokens = [await usb_client.token_mint(f"Token {i}") for i in range(3)]
    print("Generated:", tokens)

    wifi_clients = [device.to_async_client("over_wifi", token=token.token) for token in tokens]
    if any(c is None for c in wifi_clients): raise Exception

    await wifi_clients[0].tokens_revoke(tokens[0].short_id)
    print("Revoked 0 with itself")

    try:
        await wifi_clients[0].time()
        raise Exception
    except BusyBarError:
        print("Forbidden to get time with 0")

    try:
        await wifi_clients[1].tokens_revoke(tokens[2].short_id)
        raise Exception
    except BusyBarError:
        print("Forbidden to revoke 2 with 1")

    try:
        await wifi_clients[1].tokens_delete_all()
        raise Exception
    except BusyBarError:
        print("Forbidden to revoke all with 1")
    
    print("Remaining:", await usb_client.tokens_list())

if __name__ == "__main__":
    asyncio.run(main())