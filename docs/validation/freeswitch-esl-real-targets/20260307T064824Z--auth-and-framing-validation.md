# Auth and Framing Validation

## Direct Evidence
- `freeswitch.api status` returns structured lines from FreeSWITCH runtime status.
  - Correlation: `c-697cee9402b1`
- `freeswitch.api sofia status` returns multi-line tabular output.
  - Correlation: `c-020132f39e92`
- `freeswitch.api sofia status profile internal` returns long multi-line profile payload.
  - Correlation: `c-78983cc806a3`

## Framing Assessment
The successful multi-line command outputs indicate command responses are being framed and decoded into usable payload text for these requests.

## Limitations
- This runtime surface does not expose raw ESL headers/frames, so explicit proof of:
  - `Content-Type: auth/request`
  - `command/reply` vs `api/response` demux
  is inferred, not directly observed.
