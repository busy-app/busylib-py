import os
import asyncio
import logging

from pathlib import Path

from busylib import AsyncBusyBar, types

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

"""
Фронт экран
72x16 LED matrix
RGB with 16 million colors
>800 nits
Бэк экран
Monochrome OLED
160x80 px resolution
16 gray scales
Вот тут можно посмотреть tech specs
https://busy.bar/

brg -> rgb

https://github.com/flipperdevices/bsb-firmware/blob/dev/scripts/seq2anim.py


У меня есть девайс с цветным LED экраном 72x16 и HTTP API. IP адрес девайса - 10.0.4.20. HTTP API поддерживает 2 POST запроса:
/api/assets/upload - для загрузки картинки в память девайса (картинка передается в двоичном виде). У запроса 2 параметра: app_id (текстовый id приложения) и file (имя файла).
/api/display/draw - для вывода текста и ранее загруженных картинок. Есть 3 шрифта: small (высота 5), medium (высота 7), big (высота 10). width задает ширину поля вывода текста (текст будет прокручиваться со скоростью scroll_rate, если не помещается). Пример запроса: 

"""

APP_ID = os.environ.get("APP_ID", "busylib-demo")


async def blink(client: AsyncBusyBar, duration: int = 10, high: int = 100, low: int = 10, delay: float = 0.4) -> None:
    cycles = round(duration / delay)

    for _ in range(cycles):
        await client.set_display_brightness(front=high if _ % 2 == 1 else low)
        await asyncio.sleep(delay)


async def notify(client: AsyncBusyBar, display_data: str | types.DisplayElements = "test", duration: int = 100, audio: str | Path = None) -> bool:
    if not isinstance(display_data, types.DisplayElements):
        display_data = types.DisplayElements(
        app_id=APP_ID,
        elements=[
            types.TextElement(
                timeout=duration,
                color="purple",
                id="0",
                align="center",
                type="text",
                x=36,
                y=10,
                width=72,
                text=display_data,
                display=types.DisplayName.FRONT,
                font="medium",
                scroll_rate=2000,
            )
        ],
    )

    logger.info("Playing sound and blinking brightness")
    await asyncio.gather(
        client.draw_on_display(display_data),
        # client.play_audio(app_id, sound_path),
        blink(client, duration=duration),
    )

    await client.clear_display()
    logger.info("Done")
        
    return True


async def main() -> None:
    sound_path = "demo.wav"  # файл должен быть загружен заранее через upload_asset
    message = "Съешь ещё этих мягких французских булок 🥖🥐🍞, да выпей же чаю 🍮!"

    async with AsyncBusyBar(addr="http://10.0.4.20") as client:
        await notify(client, display_data=message, audio=sound_path, duration=10)

if __name__ == "__main__":
    asyncio.run(main())
