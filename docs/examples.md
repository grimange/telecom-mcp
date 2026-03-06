# Examples

## List targets

Request:

```json
{"tool":"telecom.list_targets","args":{},"correlation_id":"c-1"}
```

## Asterisk health

Request:

```json
{"tool":"asterisk.health","args":{"pbx_id":"pbx-1"},"correlation_id":"c-2"}
```

## Snapshot

Request:

```json
{"tool":"telecom.capture_snapshot","args":{"pbx_id":"pbx-1","limits":{"max_items":100}},"correlation_id":"c-3"}
```

## Find unregistered endpoints

Request:

```json
{"tool":"telecom.endpoints","args":{"pbx_id":"pbx-1"},"correlation_id":"c-4"}
```

## Capture logs around a call failure

Request:

```json
{"tool":"telecom.logs","args":{"pbx_id":"pbx-1","grep":"hangup","tail":200,"level":"warning"},"correlation_id":"c-5"}
```

## Asterisk read-only CLI diagnostic

Request:

```json
{"tool":"asterisk.cli","args":{"pbx_id":"pbx-1","command":"core show version"},"correlation_id":"c-6"}
```

## Diff two snapshots

Request:

```json
{"tool":"telecom.diff_snapshots","args":{"snapshot_a":{"snapshot_id":"snap-a","summary":{"channels_active":1}},"snapshot_b":{"snapshot_id":"snap-b","summary":{"channels_active":2}}},"correlation_id":"c-7"}
```

## Compare two PBX targets

Request:

```json
{"tool":"telecom.compare_targets","args":{"pbx_a":"pbx-1","pbx_b":"fs-1"},"correlation_id":"c-8"}
```

## Run smoke suite

Request:

```json
{"tool":"telecom.run_smoke_test","args":{"pbx_id":"pbx-1"},"correlation_id":"c-9"}
```

## Assert target state

Request:

```json
{"tool":"telecom.assert_state","args":{"pbx_id":"pbx-1","assertion":"min_registered","params":{"value":5}},"correlation_id":"c-10"}
```

## Inspect module inventory

Request:

```json
{"tool":"asterisk.modules","args":{"pbx_id":"pbx-1"},"correlation_id":"c-11"}
```
