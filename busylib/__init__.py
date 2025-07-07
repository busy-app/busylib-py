"""
Main library for interacting with the Busy Bar API.
"""

from typing import List, Optional, Union, IO

from busylib.client import ApiClient
from busylib.types import ApiResponse
from busylib.utils import is_ipv4


class BusyBar:
    """
    Main library class for interacting with the Busy Bar API.
    """

    def __init__(self, ip: str = "10.0.4.20"):
        """
        Creates an instance of BUSY Bar.
        Initializes the API client with the provided IPv4 address.

        :param ip: The IPv4 address of the device.
        :raises ValueError: If the provided IP is not a valid IPv4 address.
        """
        if not is_ipv4(ip):
            raise ValueError(f"Incorrect IPv4: {ip}")
        self.ip = ip
        self.client = ApiClient(f"http://{self.ip}/api/")

    def upload_asset(
        self, app_id: str, file_name: str, file: Union[bytes, IO[bytes]]
    ) -> Optional[ApiResponse]:
        """
        Uploads an asset to the device.

        :param app_id: Application ID for organizing assets.
        :param file_name: Filename for the uploaded asset.
        :param file: File data to upload (bytes or file-like object).
        :return: Result of the upload operation.
        """
        return self.client.upload_asset(app_id, file_name, file)

    def delete_assets(self, app_id: str) -> Optional[ApiResponse]:
        """
        Deletes all assets for a specific application from the device.

        :param app_id: Application ID whose assets should be deleted.
        :return: Result of the delete operation.
        """
        return self.client.delete_assets(app_id)

    def draw_display(self, app_id: str, elements: List[dict]) -> Optional[ApiResponse]:
        """
        Draws elements on the device display.

        :param app_id: Application ID for organizing display elements.
        :param elements: Array of display elements (text or image).
        :return: Result of the draw operation.
        """
        return self.client.draw_display(app_id, elements)

    def clear_display(self) -> Optional[ApiResponse]:
        """
        Clears the device display.

        :return: Result of the clear operation.
        """
        return self.client.clear_display()

    def play_sound(self, app_id: str, path: str) -> Optional[ApiResponse]:
        """
        Plays an audio file from the assets directory.

        :param app_id: Application ID for organizing assets.
        :param path: Path to the audio file within the app's assets directory.
        :return: Result of the play operation.
        """
        return self.client.play_audio(app_id, path)

    def stop_sound(self) -> Optional[ApiResponse]:
        """
        Stops any currently playing audio on the device.

        :return: Result of the stop operation.
        """
        return self.client.stop_audio()
