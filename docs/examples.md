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
