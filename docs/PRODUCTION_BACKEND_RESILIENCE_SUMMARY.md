# Summary

The public assessment UI now treats backend cold starts and temporary deployment interruptions as recoverable transport failures rather than immediate terminal assessment failures. The proxy retries bounded transient conditions, and the browser recovers the existing run state before stopping. The implementation remains fail-closed for permanent configuration or connectivity failures.