# Design: simplify-mqtt-broker-input

## Context

The MQTT path spans three modules today: `app/mqtt_proto.py` (hex snapshot codec
+ per-line topics `plc/<ip>/state|status`), `app/mqtt_source.py` (subscriber with
status-topic liveness, 2 s silence timeout, LINES registry + `set_line`), and
`app/publisher.py` (retained snapshots + `online/offline` status with a retained
LWT). The dashboard target line comes from the `LINES` registry
(`app/config.py:52-86`), is surfaced through `/api/line` and `state.lines`
(`app/main.py:66-76`, `app/mqtt_source.py:179`), and is picked in a dropdown
(`app/static/index.html:254-283`). The OEE connection bar already demonstrates
the pattern this change copies for the broker: user-typed address, error status
text, browser localStorage persistence with auto-reconnect
(`app/static/index.html:488-565`).

`in-memory-count-stats` is applied first: `MqttLineSource` already carries an
`on_event` callback instead of a DSN, and `/api/stats` already reads the
in-process counter. This change builds on that state; both changes touch
`mqtt_source.py`, `main.py`, and the same tests, so sequencing matters.

## Goals / Non-Goals

**Goals:**

- One fixed topic `plc_tags`, payload `{label: bool}` for the 14
  `plc_tags.csv` labels.
- Broker target typed by the user (`IP` or `IP:port`), persisted in
  localStorage, auto-connected on page load.
- Liveness purely from snapshot silence (~1 s); no status topic, retain, or LWT.
- Preserve the baseline-on-(re)connect invariant across every broker change.

**Non-Goals:**

- No TLS, authentication, MQTT 5 features, or multiple simultaneous broker
  subscriptions.
- Direct source, OEE panel, recorder, and the amqtt broker itself are untouched.
- No broker address validation beyond `IP[:port]` syntax; DNS names are not
  explicitly supported or excluded — the field is passed through as a host
  string.

## Decisions

### D1 — Payload codec: flat label-keyed JSON, strict 14 labels

`app/mqtt_proto.py` is rewritten: `TAGS_TOPIC = "plc_tags"`, `encode_payload(raw)`
(publisher side: `raw_values(inputs, outputs)` JSON-dumped) and
`parse_payload(bytes) -> dict[str, bool]` (dashboard side). Parsing requires all
14 labels, each a `bool` (a non-boolean value is a hard `ValueError`, not a
truthy cast); unknown keys are ignored. Rationale: strictness keeps edge
detection meaningful — a typo'd label cannot silently read as `false`. The
alternative (lenient, missing = false) was rejected for exactly that reason.
`state_topic`/`status_topic`, `encode_snapshot`, and `parse_snapshot` are deleted;
`app/plc.py`'s `build_view` already accepts a `{label: bool}` dict, so the
source skips `raw_values` and feeds the parsed payload straight in.

### D2 — Liveness: silence-only, staleness_ms = 1000

`MqttLineSource` drops `_status_online`, `status_topic` handling, and the
`lines` registry entirely; `_is_stale_locked` reduces to "no packet in
`staleness_ms`". The default drops 2000 → 1000 ms: the publisher publishes every
~500 ms, so one missed second means the publisher is gone. The existing
re-baseline logic (baseline-on-connect/switch/stale-resume in `_on_message`) is
kept verbatim — a stale-period gap still re-baselines before counting resumes.
No retain flag on publisher publishes and no LWT registration; `stop()` no
longer publishes `offline`.

### D3 — Broker address as the connection identity

`MqttLineSource.__init__` takes `(broker_host, broker_port, poll_interval_ms,
on_event, staleness_ms, client_factory)`. `line_ip` is dropped; the public
identity is `broker` = `"host:port"` (this is what `/api/state` reports and what
the in-memory counter's connection identity keys on). `set_line()` is deleted;
a new broker address means rebuilding the source. The `switch()` path in
`SourceManager` is no longer an idempotent no-op when the requested source
equals the active one but the broker differs.

### D4 — API: broker rides on `/api/source`; `/api/line` deleted

`POST /api/source` accepts `{source: "mqtt", broker: "192.168.0.11[:1884]"}`.
The broker string is parsed in one place (`host[:port]`, port 1–65535, default
1883) into `(host, port)` and passed to the factory. Switching to `mqtt` with no
broker while none is active is a 400; re-submitting while active rebuilds the
source with the new address. `build_source(config, name, broker=None)` loses the
`lines` parameter and falls back to `config.mqtt_broker_host/port` only if a
default is still configured — after this change, those config fields are gone,
so `broker=None` in MQTT mode means "build nothing": `SourceManager` supports an
inactive MQTT slot (startup `DATA_SOURCE=mqtt` before any submit), exposed as a
`connecting` snapshot with `broker: null`. Alternative considered — a dedicated
`POST /api/mqtt` endpoint — rejected: `/api/source` already owns the
switch/rebuild lifecycle and clearing semantics.

### D5 — Config: `MQTT_BROKER_*` and `LINES` deleted

`Config` loses `mqtt_broker_host`, `mqtt_broker_port`, and `lines`;
`load_config()`'s MQTT block (config.py:75-86) and `_parse_lines` disappear.
`DATA_SOURCE` keeps only validating `direct|mqtt`. `BROKER_HOST/BROKER_PORT`
(the line-PC publisher's target) stay. `.env.example` drops the MQTT mode
section and `LINES`.

### D6 — Publisher: same loop, new payload

`LinePublisher` keeps its read-retry loop and snap7 reader; the publish call
becomes `publish(TAGS_TOPIC, encode_payload(raw_values(inputs, outputs)),
qos=0)` — no retain, no `will_set`, no status publishes on connect/shutdown.
The payload mapping reuses `app.tags.raw_values`, so label coverage is
guaranteed by the tag map, not by publisher-local code.

### D7 — Frontend: text input + Connect replaces the dropdown

The topbar's `#line-select`/`#line-label` become a text input `#mqtt-broker`
(placeholder `192.168.0.11[:1883]`) shown only in MQTT mode, plus a Connect
button that POSTs `/api/source {source: "mqtt", broker: ...}` (also on Enter).
The localStorage key (e.g. `mqtt-broker`) stores the submitted string; on page
load it pre-fills the field and auto-connects. `renderLineControls` stops
managing a dropdown; the connection state (connecting/stale banner, broker
label) comes from `/api/state`. Stats polling keys off the active connection
reported by the backend rather than a locally tracked `selectedLine`.

## Risks / Trade-offs

- [Protocol break orphans old publishers] → Publisher and dashboard are
  deployed per line PC together; README documents the upgrade order. Old
  payloads on `plc/<ip>/state` are simply never subscribed.
- [1 s staleness may flap on a congested Wi-Fi link] → The publisher's 500 ms
  cadence gives 2× headroom; if field flapping appears, raising
  `DEFAULT_STALENESS_MS` is a one-constant tweak with no semantic change.
- [No LWT means a crashed publisher looks "live" for up to 1 s] → Accepted; the
  previous system's `offline` LWT bought at most a 2 s faster stale flag at the
  cost of a whole status topic.
- [Inactive-MQTT-slot state in SourceManager] → Only reachable at startup with
  `DATA_SOURCE=mqtt` and no submit; represented uniformly as a
  connecting/stale snapshot so the UI needs no special case beyond hiding the
  banner text's broker name.
- [localStorage stores an unvalidated string] → Same exposure as the OEE bar;
  the server validates and rejects malformed brokers with a 400, surfaced in the
  UI status text.

## Migration Plan

1. Apply `in-memory-count-stats` (already done per plan).
2. Land backend + publisher + config changes and tests in one series.
3. Update `.env.example`, README, AGENTS.md; remove `LINES`/`MQTT_BROKER_*`
   from real `.env` files.
4. Per line PC: stop publisher, pull, restart publisher (new payload); the
   dashboard restarts with it. Rollback = redeploy the previous pair.

## Open Questions

None — all decisions were settled during exploration (publisher rewritten in
repo, optional `:port`, no retain, strict payload, connecting-until-typed,
localStorage persistence).
