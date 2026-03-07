# Error Taxonomy Validation

## Validated Cases
1. Unsupported API command
- Input: `bgapi status`
- Correlation: `c-0ce9334915a8`
- Result: `NOT_ALLOWED` (expected)

2. Unsupported API command variant
- Input: `status foo`
- Correlation: `c-3f42a5c31b70`
- Result: `NOT_ALLOWED` (expected)

3. Missing resource
- Input: `uuid_dump 00000000-0000-0000-0000-000000000000` via `freeswitch.channel_details`
- Correlation: `c-433961005ca8`
- Result: `NOT_FOUND` (expected)

4. Upstream runtime failure
- Input: `freeswitch.health`
- Correlations: `c-07567a08050f`, `c-899ec50afd59`
- Result: `UPSTREAM_ERROR` (`TypeError`)

## Not Directly Validated in This Run
- Authentication failure with incorrect ESL secret.
- Forced network connection failure for live configured target.
- Parser corruption/malformed frame mapping.

These require either controlled negative test plumbing or temporary validation targets.
