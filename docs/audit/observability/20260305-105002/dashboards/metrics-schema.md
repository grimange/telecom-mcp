# Metrics Schema

- tool_latency_ms: histogram (per tool_name)
- tool_error_count: counter (tool_name + error_code)
- connector_reconnect_count: counter (connector + target)
- tool_rate_limited_count: counter (tool_name + scope)
