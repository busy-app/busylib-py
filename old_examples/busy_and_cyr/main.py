import logging

from busylib import BusyBar


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
sh = logging.StreamHandler()
logger.addHandler(sh)


if __name__ == "__main__":
    with BusyBar(addr="http://10.0.4.20") as client:
        logger.info("BUSY bar status: %s", client.get_status())

        display_data = {
            "app_id": "busybar-demo",
            "elements": [
                {
                    "id": "0",
                    "timeout": 30,
                    "align": "center",
                    "x": 36,
                    "y": 10,
                    "type": "text",
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
