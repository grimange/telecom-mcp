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

## Run SIP registration triage for endpoint 1001

Request:

```json
{"tool":"telecom.run_playbook","args":{"name":"sip_registration_triage","pbx_id":"pbx-1","endpoint":"1001"},"correlation_id":"c-9b"}
```

## Run baseline smoke on PBX target

Request:

```json
{"tool":"telecom.run_smoke_suite","args":{"name":"baseline_read_only_smoke","pbx_id":"pbx-1"},"correlation_id":"c-9c"}
```

## Compare PBX-A and PBX-B for drift

Request:

```json
{"tool":"telecom.run_playbook","args":{"name":"pbx_drift_comparison","pbx_a":"pbx-1","pbx_b":"fs-1"},"correlation_id":"c-9d"}
```

## Run outbound failure triage after a failed test call

Request:

```json
{"tool":"telecom.run_playbook","args":{"name":"outbound_call_failure_triage","pbx_id":"pbx-1","endpoint":"1001","destination_hint":"18005550199"},"correlation_id":"c-9e"}
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

## Interpret playbook and smoke results

Playbook result keys:
- `playbook`, `status`, `bucket`, `summary`, `steps`, `evidence`, `warnings`, `failed_sources`

Smoke result keys:
- `suite`, `status`, `summary`, `checks`, `counts`, `warnings`, `failed_sources`

## Create baseline

Request:

```json
{"tool":"telecom.baseline_create","args":{"pbx_id":"pbx-1","baseline_id":"prod-asterisk-v1"},"correlation_id":"c-12"}
```

## Run audit

Request:

```json
{"tool":"telecom.audit_target","args":{"pbx_id":"pbx-1","baseline_id":"prod-asterisk-v1"},"correlation_id":"c-13"}
```

## Compare drift against baseline

Request:

```json
{"tool":"telecom.drift_target_vs_baseline","args":{"pbx_id":"pbx-1","baseline_id":"prod-asterisk-v1"},"correlation_id":"c-14"}
```

## Export audit report as markdown

Request:

```json
{"tool":"telecom.audit_export","args":{"pbx_id":"pbx-1","format":"markdown"},"correlation_id":"c-15"}
```
