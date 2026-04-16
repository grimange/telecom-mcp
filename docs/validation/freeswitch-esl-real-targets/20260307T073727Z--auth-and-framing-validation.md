# Auth and Framing Validation

## Direct Evidence
- `freeswitch.api status`: `c-4cbac0983413`
- `freeswitch.api sofia status`: `c-3a5527d65fc9`
- `freeswitch.api sofia status profile internal`: `c-77b4e6f36a4c`

## Inference
Successful command execution implies working auth + framed response path.

## Limitation
Current tool surface does not expose raw auth frames (`auth/request` / auth `command/reply`) directly; this remains inferred from command success and connector contract behavior.
