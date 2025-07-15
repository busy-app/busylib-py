import pytest
import requests
import requests_mock
from busylib.client import ApiClient

BASE_URL = "http://test.com"


@pytest.fixture
def api_client():
    return ApiClient(BASE_URL)


@pytest.fixture
def mocked_requests():
    with requests_mock.Mocker() as m:
        yield m


def test_upload_asset(api_client, mocked_requests):
    app_id = "test_app"
    file_name = "test_file.png"
    file_content = b"test content"
    mocked_requests.post(f"{BASE_URL}/v0/assets/upload", status_code=204)

    api_client.upload_asset(app_id, file_name, file_content)

    assert mocked_requests.called
    last_request = mocked_requests.last_request
    assert last_request.method == "POST"
    assert last_request.qs["app_id"] == [app_id]
    assert last_request.qs["file"] == [file_name]
    assert last_request.body == file_content


def test_delete_assets(api_client, mocked_requests):
    app_id = "test_app"
    mocked_requests.delete(f"{BASE_URL}/v0/assets/upload", status_code=204)

    api_client.delete_assets(app_id)

    assert mocked_requests.called
    last_request = mocked_requests.last_request
    assert last_request.method == "DELETE"
    assert last_request.qs["app_id"] == [app_id]


def test_play_audio(api_client, mocked_requests):
    app_id = "test_app"
    path = "test.mp3"
    mocked_requests.post(f"{BASE_URL}/v0/audio/play", status_code=204)

    api_client.play_audio(app_id, path)

    assert mocked_requests.called
    last_request = mocked_requests.last_request
    assert last_request.method == "POST"
    assert last_request.qs["app_id"] == [app_id]
    assert last_request.qs["path"] == [path]


def test_stop_audio(api_client, mocked_requests):
    mocked_requests.delete(f"{BASE_URL}/v0/audio/play", status_code=204)

    api_client.stop_audio()

    assert mocked_requests.called
    last_request = mocked_requests.last_request
    assert last_request.method == "DELETE"


def test_draw_display(api_client, mocked_requests):
    app_id = "test_app"
    elements = [{"type": "text", "value": "Hello"}]
    mocked_requests.post(f"{BASE_URL}/v0/display/draw", status_code=204)

    api_client.draw_display(app_id, elements)

    assert mocked_requests.called
    last_request = mocked_requests.last_request
    assert last_request.method == "POST"
    json_body = last_request.json()
    assert json_body["app_id"] == app_id
    assert len(json_body["elements"]) == 1
    assert json_body["elements"][0]["value"] == "Hello"


def test_clear_display(api_client, mocked_requests):
    mocked_requests.delete(f"{BASE_URL}/v0/display/draw", status_code=204)

    api_client.clear_display()

    assert mocked_requests.called
    last_request = mocked_requests.last_request
    assert last_request.method == "DELETE"


def test_request_failure(api_client, mocked_requests):
    mocked_requests.get(
        f"{BASE_URL}/v0/some/endpoint", exc=requests.exceptions.ConnectionError
    )
    with pytest.raises(ConnectionError):
        api_client.get("v0/some/endpoint")
