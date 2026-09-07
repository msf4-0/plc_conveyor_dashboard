import pytest

from app.config import _parse_lines, load_config


BASE_ENV = {
    "PLC_IP": "192.168.5.3",
    "PLC_RACK": "0",
    "PLC_SLOT": "1",
    "POLL_INTERVAL_MS": "500",
    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/plc_dashboard",
    "HOST": "127.0.0.1",
    "PORT": "8000",
}


@pytest.fixture()
def env(monkeypatch):
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    for key in ("DATA_SOURCE", "MQTT_BROKER_HOST", "MQTT_BROKER_PORT", "LINES", "BROKER_PORT"):
        monkeypatch.delenv(key, raising=False)


def test_direct_mode_defaults(env):
    cfg = load_config()
    assert cfg.data_source == "direct"
    assert cfg.plc_ip == "192.168.5.3"
    assert cfg.lines is None


def test_mqtt_mode_requires_broker(env, monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mqtt")
    with pytest.raises(RuntimeError):
        load_config()
    monkeypatch.setenv("MQTT_BROKER_HOST", "192.168.0.11")
    monkeypatch.setenv("MQTT_BROKER_PORT", "1883")
    cfg = load_config()
    assert cfg.data_source == "mqtt"
    assert (cfg.mqtt_broker_host, cfg.mqtt_broker_port) == ("192.168.0.11", 1883)


def test_mqtt_mode_registry_provides_default_broker(env, monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mqtt")
    monkeypatch.setenv("LINES", "10.0.0.1=h1:1884")
    cfg = load_config()  # no MQTT_BROKER_* needed
    assert (cfg.mqtt_broker_host, cfg.mqtt_broker_port) == ("h1", 1884)
    monkeypatch.setenv("MQTT_BROKER_PORT", "1885")  # explicit override still wins
    assert load_config().mqtt_broker_port == 1885


def test_direct_mode_with_lines_registry_still_boots(env, monkeypatch):
    monkeypatch.setenv("LINES", "10.0.0.1=h1:1884")  # no DATA_SOURCE, no MQTT_BROKER_*
    cfg = load_config()
    assert cfg.data_source == "direct"
    assert (cfg.mqtt_broker_host, cfg.mqtt_broker_port) == ("h1", 1884)
    assert cfg.lines == {"10.0.0.1": ("h1", 1884)}


def test_invalid_data_source_rejected(env, monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "modbus")
    with pytest.raises(ValueError):
        load_config()


def test_lines_registry_parsed(env, monkeypatch):
    monkeypatch.setenv("LINES", " 192.168.0.1=192.168.0.11:1883 , 192.168.0.2=hostB:1884 ")
    cfg = load_config()
    assert cfg.lines == {
        "192.168.0.1": ("192.168.0.11", 1883),
        "192.168.0.2": ("hostB", 1884),
    }


@pytest.mark.parametrize(
    "raw",
    [
        "192.168.0.1",  # no '='
        "192.168.0.1=hostA",  # no port
        "192.168.0.1=hostA:abc",  # non-numeric port
        "192.168.0.1=hostA:1883,192.168.0.1=hostB:1883",  # duplicate PLC IP
    ],
)
def test_lines_registry_invalid(env, monkeypatch, raw):
    monkeypatch.setenv("LINES", raw)
    with pytest.raises(ValueError):
        load_config()


def test_broker_port_default_and_override(env, monkeypatch):
    assert load_config().broker_port == 1883
    monkeypatch.setenv("BROKER_PORT", "1884")
    assert load_config().broker_port == 1884


def test_parse_lines_directly():
    assert _parse_lines("a=host:1") == {"a": ("host", 1)}
    assert _parse_lines("") == {}
