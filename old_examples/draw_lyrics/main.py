import time
import logging

from .settings import busy_settings

from busylib import BusyBar


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
sh = logging.StreamHandler()
logger.addHandler(sh)


LYRICS = (
    "Съешь ещё этих мягких французских булок 🥖🥐🍞, да выпей же чаю 🍮!"
)


if __name__ == "__main__":
    with BusyBar(addr=str(busy_settings.address)) as client:
        logger.info("BUSY bar status: %s", client.get_status())

        display_data = {
            "app_id": busy_settings.app_id,
            "elements": [
                {
                    "id": "0",
                    "type": "text",
                    "timeout": 30,
                    "align": "center",
                    "x": 0,
                    "y": 36,
                    "text": "Съешь ещё этих мягких французских булок 🥖🥐🍞, да выпей же чаю 🍮!",
                    "font": "medium",  # small | medium | medium_condensed | big
                    "color": "#FFFFFFFF",
                    "width": 72,
                    "scroll_rate": 2000,
                    "display": "front"
                },
                {
                    "id": "1",
                    "timeout": 6,
                    "align": "top_mid",
                    "x": 36,
                    "y": 0,
                    "type": "text",
                    "text": "lyrics",
                    "font": "small",
                    "color": "#AAFF00FF",
                    "display": "front"
                },
                {
                    "id": "2",
                    "timeout": 6,
                    "type": "image",
                    "path": "data.png",
                    "x": 0,
                    "y": 0,
                    "display": "front"
                }
            ],
        }

        client.draw_on_display(display_data)

    logger.info("Done")
