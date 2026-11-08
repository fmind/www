"""Configuration boundary tests."""

import pytest
from granian.constants import Interfaces

import www.__main__ as main_module
from www.__main__ import build_server
from www.config import Config, Environment


def test_load_defaults() -> None:
    config = Config.load({})

    assert config == Config(environment=Environment.DEVELOPMENT, port=8080)


def test_load_production() -> None:
    environ = {
        "ENVIRONMENT": "production",
        "HOST": "0.0.0.0",  # noqa: S104 - the image's listener.
        "PORT": "9090",
        "GOOGLE_CLOUD_PROJECT": "example-project",
    }
    config = Config.load(environ)

    assert config == Config(
        environment=Environment.PRODUCTION,
        host="0.0.0.0",  # noqa: S104 - the image's listener.
        port=9090,
        google_cloud_project="example-project",
    )


@pytest.mark.parametrize(
    ("environ", "message"),
    [
        ({"ENVIRONMENT": ""}, "invalid ENVIRONMENT"),
        ({"ENVIRONMENT": "staging"}, "invalid ENVIRONMENT"),
        ({"HOST": ""}, "invalid HOST"),
        ({"HOST": "localhost"}, "invalid HOST"),
        ({"PORT": ""}, "invalid PORT"),
        ({"PORT": "not-a-port"}, "invalid PORT"),
        ({"PORT": "70000"}, "invalid PORT"),
        # The project names the Cloud Logging trace resource, so reject anything but a project ID.
        ({"GOOGLE_CLOUD_PROJECT": "short"}, "invalid GOOGLE_CLOUD_PROJECT"),
        ({"GOOGLE_CLOUD_PROJECT": "Example-Project"}, "invalid GOOGLE_CLOUD_PROJECT"),
        ({"GOOGLE_CLOUD_PROJECT": "example-project-"}, "invalid GOOGLE_CLOUD_PROJECT"),
        ({"GOOGLE_CLOUD_PROJECT": "example/traces/x"}, "invalid GOOGLE_CLOUD_PROJECT"),
        ({"GOOGLE_CLOUD_PROJECT": "a" * 31}, "invalid GOOGLE_CLOUD_PROJECT"),
    ],
)
def test_load_rejects_invalid_values(environ: dict[str, str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Config.load(environ)


def test_server_runtime_bounds_slow_headers_and_cloud_run_shutdown() -> None:
    log_dictconfig: dict[str, object] = {"version": 1}
    server = build_server(Config(port=9090), log_dictconfig=log_dictconfig)

    assert server.target == "www.app:app"
    assert server.bind_addr == "127.0.0.1"
    assert server.bind_port == 9090
    assert server.interface is Interfaces.ASGI
    assert server.websockets is False
    assert server.http1_settings is not None
    assert server.http1_settings.header_read_timeout == 5_000
    assert server.workers_kill_timeout == 8
    assert server.log_config is log_dictconfig


def test_main_configures_process_logging_before_serving(monkeypatch: pytest.MonkeyPatch) -> None:
    config = Config(environment=Environment.PRODUCTION, port=9090)
    log_dictconfig: dict[str, object] = {"version": 1}
    configured: list[Config] = []
    observed: list[tuple[Config, dict[str, object]]] = []
    served: list[bool] = []

    class RecordingServer:
        def serve(self) -> None:
            served.append(True)

    def configure_process_logging(loaded: Config) -> dict[str, object]:
        configured.append(loaded)
        return log_dictconfig

    def record_build(loaded: Config, *, log_dictconfig: dict[str, object]) -> RecordingServer:
        observed.append((loaded, log_dictconfig))
        return RecordingServer()

    monkeypatch.setattr(main_module.Config, "load", lambda: config)
    monkeypatch.setattr(main_module, "stdlib_logging_config", configure_process_logging)
    monkeypatch.setattr(main_module, "build_server", record_build)

    main_module.main()

    assert configured == [config]
    assert observed == [(config, log_dictconfig)]
    assert served == [True]
