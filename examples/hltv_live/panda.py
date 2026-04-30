import httpx
import asyncio


API_KEY = "cS_eHuUFjMhcL9DADBmKCAf1jcBNCK5zK2aihADpS0nVxcgOIw0"
GAME = "csgo"


async def get_upcoming_matches(limit: int = 10):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
    }
    params = {
        "sort": "begin_at",
        "page[size]": limit,
    }

    async with httpx.AsyncClient(
        base_url="https://api.pandascore.co",
        headers=headers,
        timeout=10.0,
    ) as client:
        resp = await client.get(f"/{GAME}/matches/upcoming", params=params)
        resp.raise_for_status()
        return resp.json()


async def main():
    matches = await get_upcoming_matches()
    for m in matches:
        print(m["name"], m["begin_at"], m)


asyncio.run(main())
