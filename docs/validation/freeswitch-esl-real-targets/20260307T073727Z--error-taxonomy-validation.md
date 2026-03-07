# Error Taxonomy Validation

## Verified Cases
1. Blocked command (`bgapi status`)
- Correlation: `c-661416c02659`
- Result: `NOT_ALLOWED`

2. Blocked command variant (`status foo`)
- Correlation: `c-eb0677ff0bc6`
- Result: `NOT_ALLOWED`

3. Missing channel (`uuid_dump` via `freeswitch.channel_details`)
- Correlation: `c-b32355bd033c`
- Result: `NOT_FOUND`

4. Invalid Sofia profile parameter
- Correlation: `c-7ca4e51dd956`
- Result: tool returns partial payload with `Invalid Profile!` in raw output, not an error envelope.

5. Upstream runtime exception path
- Correlation: `c-f54a586af47f`
- Result: `UPSTREAM_ERROR` (`TypeError`)

## Not Covered This Run
- Authentication failure classification with bad credentials.
- Forced transport connection failure classification for live configured target.
