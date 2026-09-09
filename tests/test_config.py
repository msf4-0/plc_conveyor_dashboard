import pytest

from app.config import load_config, load_recorder_config


BASE_ENV = {
    "PLC_IP": "192.168.5.3",
    "PLC_RACK": "0",
    "PLC_SLOT": "1",
    "POLL_INTERVAL_MS": "500",
    "HOST": "127.0.0.1",
    "PORT": "8000",
}

RECORDER_ENV = {
    "PLC_IP": "192.168.5.3",
    "PLC_RACK": "0",
    "PLC_SLOT": "1",
    "POLL_INTERVAL_MS": "500",
    "OEE_DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/oee",
}


@pytest.fixture()
def env(monkeypatch):
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    for key in ("DATA_SOURCE", "MQTT_BROKER_HOST", "MQTT_BROKER_PORT", "LINES", "BROKER_PORT"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def recorder_env(monkeypatch):
    for key, value in RECORDER_ENV.items():
        monkeypatch.setenv(key, value)
    for key in ("DATABASE_URL", "HOST", "PORT", "IDEAL_CYCLE_TIME_S", "OEE_WRITE_INTERVAL_S"):
        monkeypatch.delenv(key, raising=False)


def test_direct_mode_defaults(env):
    cfg = load_config()
    assert cfg.data_source == "direct"
    assert cfg.plc_ip == "192.168.5.3"
    assert (cfg.broker_host, cfg.broker_port) == ("127.0.0.1", 1883)


def test_mqtt_mode_needs_no_broker_config(env, monkeypatch):
    # the broker address is typed in the dashboard at runtime
    monkeypatch.setenv("DATA_SOURCE", "mqtt")
    cfg = load_config()
    assert cfg.data_source == "mqtt"


def test_mqtt_broker_env_vars_ignored(env, monkeypatch):
    # the old MQTT_BROKER_*/LINES variables no longer exist in config
    monkeypatch.setenv("MQTT_BROKER_HOST", "192.168.0.11")
    monkeypatch.setenv("MQTT_BROKER_PORT", "1883")
    monkeypatch.setenv("LINES", "10.0.0.1=h1:1884")
    cfg = load_config()
    assert not hasattr(cfg, "lines")
    assert not hasattr(cfg, "mqtt_broker_host")


def test_invalid_data_source_rejected(env, monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "modbus")
    with pytest.raises(ValueError):
        load_config()


def test_broker_port_default_and_override(env, monkeypatch):
    assert load_config().broker_port == 1883
    monkeypatch.setenv("BROKER_PORT", "1884")
    assert load_config().broker_port == 1884


def test_missing_required_var_fails_fast(env, monkeypatch):
    monkeypatch.delenv("PLC_IP")
    with pytest.raises(RuntimeError):
        load_config()


# -- recorder configuration -------------------------------------------------


def test_recorder_config_defaults(recorder_env):
    cfg = load_recorder_config()
    assert cfg.oee_database_url == RECORDER_ENV["OEE_DATABASE_URL"]
    assert cfg.write_interval_s == 1.0
    assert cfg.ideal_cycle_time_s == 5.0
    assert cfg.plc_ip == "192.168.5.3"
    assert (cfg.plc_rack, cfg.plc_slot) == (0, 1)
    assert cfg.poll_interval_ms == 500


def test_recorder_config_ignores_dashboard_vars(recorder_env):
    # HOST/PORT are the dashboard's; the recorder must not need them
    cfg = load_recorder_config()
    assert cfg.oee_database_url.startswith("postgresql://")


def test_recorder_config_missing_oee_dsn_fails_fast(recorder_env, monkeypatch):
    monkeypatch.delenv("OEE_DATABASE_URL")
    with pytest.raises(RuntimeError):
        load_recorder_config()


def test_recorder_config_missing_plc_vars_fail_fast(monkeypatch):
    for key, value in RECORDER_ENV.items():
        if key != "PLC_IP":
            monkeypatch.setenv(key, value)
    monkeypatch.delenv("PLC_IP", raising=False)
    with pytest.raises(RuntimeError):
        load_recorder_config()


def test_recorder_config_overrides(recorder_env, monkeypatch):
    monkeypatch.setenv("OEE_WRITE_INTERVAL_S", "10")
    monkeypatch.setenv("IDEAL_CYCLE_TIME_S", "2.5")
    cfg = load_recorder_config()
    assert cfg.write_interval_s == 10.0
    assert cfg.ideal_cycle_time_s == 2.5


@pytest.mark.parametrize("bad", ["0", "-1", "0.05", "3600.1", "abc"])
def test_recorder_config_invalid_values_rejected(recorder_env, monkeypatch, bad):
    monkeypatch.setenv("IDEAL_CYCLE_TIME_S", bad)
    with pytest.raises((ValueError, RuntimeError)):
        load_recorder_config()


def test_recorder_config_invalid_write_interval_rejected(recorder_env, monkeypatch):
    for bad in ("0", "-2", "abc"):
        monkeypatch.setenv("OEE_WRITE_INTERVAL_S", bad)
        with pytest.raises((ValueError, RuntimeError)):
            load_recorder_config()
