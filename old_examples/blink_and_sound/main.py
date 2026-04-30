import logging
import time

from busylib import BusyBar, types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    with BusyBar(addr="http://10.0.4.20") as client:
        message = "Съешь ещё этих мягких французских булок 🥖🥐🍞"

        display_data = types.DisplayElements(
            app_id="busylib-demo",
            elements=[
                types.TextElement(
                    id="msg",
                    type="text",
                    x=0,
                    y=10,
                    text=message,
                    display=types.DisplayName.FRONT,
                    font="medium",
                )
            ],
        )

        logger.info("Drawing message")
        client.draw_on_display(display_data)

        # Запускаем звук (файл должен быть загружен заранее через upload_asset).
        sound_path = "notify.snd"
        logger.info("Playing sound: %s", sound_path)
        client.play_audio(display_data.app_id, sound_path)

        # Моргаем яркостью фронтального дисплея.
        logger.info("Blinking front display brightness")
        for _ in range(5):
            client.set_display_brightness(front=100)
            time.sleep(0.4)
            client.set_display_brightness(front=10)
            time.sleep(0.4)

        logger.info("Done")


if __name__ == "__main__":
    main()
