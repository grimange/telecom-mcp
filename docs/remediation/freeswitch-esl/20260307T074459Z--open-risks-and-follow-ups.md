# Open Risks and Follow-Ups

## Open Risks
1. Runtime deployment drift can keep health/version behavior inconsistent with repository code.
2. BGAPI semantics remain unvalidated due policy scope.
3. Live negative-path coverage (auth failure / forced connection failure) is still limited.

## Follow-Ups
1. Deploy current repository head to the runtime that serves MCP calls.
2. Re-run `docs/prompts/freeswitch/03-esl-validation.md` and compare results.
3. Add runtime parity checks to fail fast when deployed behavior diverges from repository expectations.
4. Decide BGAPI support posture and implement gated path if required.
