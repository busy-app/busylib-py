import time
import logging

from .settings import busy_settings

from busylib import BusyBar


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
sh = logging.StreamHandler()
logger.addHandler(sh)


WEEWOO_LENGTH = 10
WEEWOO_RATE = 0.5
WEEWOO_HIBRIGHT = 100
WEEWOO_LOBRIGHT = 10


if __name__ == "__main__":
    with BusyBar(addr=str(busy_settings.address)) as client:
        logger.info("BUSY bar status: %s", client.get_status())

        brightness = client.get_display_brightness()
        logger.info("Brightness: %s; %s", brightness.front, brightness.back)

        for i in range(WEEWOO_LENGTH):
            client.set_display_brightness(front=WEEWOO_HIBRIGHT if i % 2 == 0 else WEEWOO_LOBRIGHT)
            time.sleep(WEEWOO_RATE)
        
        client.set_display_brightness(
            front=brightness.front, 
            back=brightness.back,
        )

    logger.info("Done")
