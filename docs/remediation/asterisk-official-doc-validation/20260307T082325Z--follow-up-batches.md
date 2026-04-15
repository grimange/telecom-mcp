# Follow-Up Batches

## F1
- Priority: High
- Title: Deploy and validate remediated AMI contract behavior on real target
- Prerequisites:
  - Deploy/restart MCP runtime with this commit
  - Access to `pbx-1`
- Validation surface:
  - `asterisk.pjsip_show_registration`
  - `asterisk.core_show_channel`
  - `asterisk.modules`
  - `asterisk.pjsip_show_contacts`

## F2
- Priority: Medium
- Title: Add doc-pinned fixture corpus for AMI command framing variants
- Prerequisites:
  - capture additional AMI `Command` traces from Asterisk 22.x
- Validation surface:
  - connector parser completeness
  - command wrapper consistency

## F3
- Priority: Medium
- Title: Close dialplan/ARI lifecycle verification gap
- Prerequisites:
  - target dialplan snippets (`Dial`, `Stasis`)
  - ARI websocket traces with `StasisStart`/`StasisEnd`
- Validation surface:
  - docs-contract assertions for lifecycle ordering and continuation behavior
