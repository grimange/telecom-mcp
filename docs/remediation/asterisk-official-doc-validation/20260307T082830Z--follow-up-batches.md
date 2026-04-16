# Follow-Up Batches

## F1
- Priority: High
- Title: Collect live dialplan and ARI lifecycle evidence for `DR-005`
- Prerequisites:
  - accessible Asterisk target with representative dialplan
  - ARI websocket capture path
- Estimated validation surface:
  - `dialplan-validation`
  - `ari-validation`
  - lifecycle sequence assertions

## F2
- Priority: Medium
- Title: Run live-target post-deploy verification for resolved AMI drift items
- Prerequisites:
  - deploy/restart MCP runtime on target environment
- Estimated validation surface:
  - `asterisk.pjsip_show_registration`
  - `asterisk.core_show_channel`
  - `asterisk.modules`
  - `asterisk.pjsip_show_contacts`

## F3
- Priority: Medium
- Title: Extend AMI command fixture corpus across Asterisk minor versions
- Prerequisites:
  - capture additional `Command` traces from target versions
- Estimated validation surface:
  - connector response completion
  - command output normalization
