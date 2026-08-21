from dataclasses import dataclass


def _positive_int(value, default):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return max(1, int(default))


@dataclass(frozen=True)
class JudgePolicy:
    max_workers: int
    queue_maxsize: int
    max_time_limit_ms: int
    max_memory_limit_mb: int
    max_output_size: int
    max_processes: int
    max_workspace_bytes: int
    max_workspace_files: int
    sandbox_enabled: bool
    sandbox_required: bool

    @classmethod
    def from_config(cls, config):
        sandbox_enabled = bool(config.get('SANDBOX_ENABLED', True))
        sandbox_required = bool(config.get('JUDGE_REQUIRE_SANDBOX', True))
        if sandbox_required and not sandbox_enabled:
            raise ValueError('sandbox is required for this judge configuration')
        if (
            sandbox_required
            and bool(config.get('SANDBOX_STRICT_APP_CONTAINER', True))
            and not bool(config.get('SANDBOX_APP_CONTAINER', True))
        ):
            raise ValueError('AppContainer is required for this judge configuration')

        worker_cap = _positive_int(config.get('JUDGE_WORKER_CAP', 8), 8)
        max_workers = min(_positive_int(config.get('MAX_JUDGE_WORKERS', 1), 1), worker_cap)
        return cls(
            max_workers=max_workers,
            queue_maxsize=min(
                _positive_int(config.get('JUDGE_QUEUE_MAXSIZE', 200), 200),
                10000,
            ),
            max_time_limit_ms=min(
                _positive_int(config.get('MAX_TIME_LIMIT_MS', 20000), 20000),
                120000,
            ),
            max_memory_limit_mb=min(
                _positive_int(config.get('MAX_MEMORY_LIMIT_MB', 512), 512),
                2048,
            ),
            max_output_size=min(
                _positive_int(config.get('MAX_OUTPUT_SIZE', 64 * 1024), 64 * 1024),
                4 * 1024 * 1024,
            ),
            max_processes=min(
                _positive_int(config.get('SANDBOX_MAX_PROCESSES', 8), 8),
                32,
            ),
            max_workspace_bytes=min(
                _positive_int(
                    config.get('SANDBOX_MAX_WORKSPACE_BYTES', 64 * 1024 * 1024), 64 * 1024 * 1024
                ),
                512 * 1024 * 1024,
            ),
            max_workspace_files=min(
                _positive_int(config.get('SANDBOX_MAX_WORKSPACE_FILES', 1024), 1024),
                10000,
            ),
            sandbox_enabled=sandbox_enabled,
            sandbox_required=sandbox_required,
        )
