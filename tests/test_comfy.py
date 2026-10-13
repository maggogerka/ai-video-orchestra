from __future__ import annotations

import json

import httpx

from video_orchestra.comfy import ComfyClient


class FakeWebSocket:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = [json.dumps(message) for message in messages]
        self.closed = False
        self.timeouts: list[float] = []

    def recv(self) -> str:
        return self.messages.pop(0)

    def settimeout(self, timeout: float) -> None:
        self.timeouts.append(timeout)

    def close(self) -> None:
        self.closed = True


def test_client_uses_http_and_websocket_and_downloads_video(tmp_path):
    prompt_id = "prompt-123"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST" and request.url.path == "/prompt":
            payload = json.loads(request.content)
            assert payload["client_id"] == "client-abc"
            assert payload["prompt"] == {"1": {"class_type": "Test", "inputs": {}}}
            return httpx.Response(200, json={"prompt_id": prompt_id})
        if request.url.path == f"/history/{prompt_id}":
            return httpx.Response(
                200,
                json={
                    prompt_id: {
                        "outputs": {
                            "save": {
                                "videos": [
                                    {
                                        "filename": "result.mp4",
                                        "subfolder": "generated",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                },
            )
        if request.url.path == "/view":
            assert request.url.params["filename"] == "result.mp4"
            assert request.url.params["subfolder"] == "generated"
            return httpx.Response(200, content=b"fake-mp4")
        return httpx.Response(404)

    socket = FakeWebSocket(
        [
            {"type": "execution_start", "data": {"prompt_id": "someone-else"}},
            {"type": "execution_start", "data": {"prompt_id": prompt_id}},
            {"type": "executing", "data": {"prompt_id": prompt_id, "node": None}},
        ]
    )
    websocket_urls: list[str] = []

    def ws_factory(url: str, **_kwargs):
        websocket_urls.append(url)
        return socket

    http_client = httpx.Client(
        base_url="http://127.0.0.1:8188/", transport=httpx.MockTransport(handler)
    )
    generating: list[bool] = []
    client = ComfyClient(
        "http://127.0.0.1:8188",
        client_id="client-abc",
        http_client=http_client,
        ws_factory=ws_factory,
    )

    actual_prompt_id = client.queue_prompt({"1": {"class_type": "Test", "inputs": {}}})
    client.wait_for_completion(actual_prompt_id, on_generating=lambda: generating.append(True))
    history = client.get_history(actual_prompt_id)
    output = client.find_output(history)
    destination = tmp_path / "scene.mp4"
    client.download_output(output, destination)

    assert actual_prompt_id == prompt_id
    assert generating == [True]
    assert websocket_urls == ["ws://127.0.0.1:8188/ws?clientId=client-abc"]
    assert socket.closed
    assert destination.read_bytes() == b"fake-mp4"
    assert [request.url.path for request in requests] == [
        "/prompt",
        f"/history/{prompt_id}",
        "/view",
    ]


def test_find_output_supports_files_collection():
    history = {
        "outputs": {
            "node": {
                "files": [{"filename": "movie.webm", "subfolder": "", "type": "output"}]
            }
        }
    }

    assert ComfyClient.find_output(history)["filename"] == "movie.webm"
