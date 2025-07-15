"""
Main library for interacting with the Busy Bar API.
"""

from typing import IO

from busylib.client import ApiClient
from busylib.types import ApiResponse


class BusyBar:
    """
    Main library class for interacting with the Busy Bar API.
    """

    def __init__(self, addr: str = "10.0.4.20"):
        """
        Creates an instance of BUSY Bar.
        Initializes the API client with the provided address.

        :param addr: The address of the device.
        """
        self._addr = addr
        self._client = ApiClient(f"http://{self._addr}/api/")

    def upload_asset(
        self, app_id: str, file_name: str, file: bytes | IO[bytes]
    ) -> ApiResponse | None:
        """
        Uploads an asset to the device.

        :param app_id: Application ID for organizing assets.
        :param file_name: Filename for the uploaded asset.
        :param file: File data to upload (bytes or file-like object).
        :return: Result of the upload operation.
        """
        return self._client.upload_asset(app_id, file_name, file)

    def delete_assets(self, app_id: str) -> ApiResponse | None:
        """
        Deletes all assets for a specific application from the device.

        :param app_id: Application ID whose assets should be deleted.
        :return: Result of the delete operation.
        """
        return self._client.delete_assets(app_id)

    def draw_display(self, app_id: str, elements: list[dict]) -> ApiResponse | None:
        """
        Draws elements on the device display.

        :param app_id: Application ID for organizing display elements.
        :param elements: Array of display elements (text or image).
        :return: Result of the draw operation.
        """
        return self._client.draw_display(app_id, elements)

    def clear_display(self) -> ApiResponse | None:
        """
        Clears the device display.

        :return: Result of the clear operation.
        """
        return self._client.clear_display()

    def play_sound(self, app_id: str, path: str) -> ApiResponse | None:
        """
        Plays an audio file from the assets directory.

        :param app_id: Application ID for organizing assets.
        :param path: Path to the audio file within the app's assets directory.
        :return: Result of the play operation.
        """
        return self._client.play_audio(app_id, path)

    def stop_sound(self) -> ApiResponse | None:
        """
        Stops any currently playing audio on the device.

        :return: Result of the stop operation.
        """
        return self._client.stop_audio()
