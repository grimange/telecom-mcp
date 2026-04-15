# Sofia Profile Validation

## Raw Command Evidence
- `freeswitch.api sofia status` (`c-3a5527d65fc9`) reports 4 profiles + 1 alias.
- `freeswitch.api sofia status profile internal` (`c-77b4e6f36a4c`) returns detailed profile data.
- `freeswitch.api sofia status profile external` (`c-7e46b5388415`) returns detailed profile data.

## Adapter Output Evidence
- `freeswitch.sofia_status` (`c-5d5dbb41a505`) parsed only subset fields:
  - profiles: 1
  - gateways: 1

## Conclusion
Sofia discovery is non-empty but still not complete relative to raw `sofia status` table output in deployed runtime.
