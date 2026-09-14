import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

try:
    from dotenv import load_dotenv
except ImportError:  # Optional during minimal tooling checks.
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(os.path.join(BASE_DIR, '.env'), override=False)


def _find_jdk_bin(base_dir):
    direct = os.path.join(base_dir, 'toolchain', 'jdk', 'bin')
    if os.path.isdir(direct):
        return direct
    jdk_root = os.path.join(base_dir, 'toolchain', 'jdk')
    if not os.path.isdir(jdk_root):
        return direct
    try:
        for name in os.listdir(jdk_root):
            candidate = os.path.join(jdk_root, name, 'bin')
            if os.path.isdir(candidate):
                return candidate
    except OSError:
        return direct
    return direct


def _find_python_exe(base_dir):
    import sys

    candidates = [
        os.path.join(base_dir, 'runtime', 'python', 'python.exe'),
        os.path.join(base_dir, 'toolchain', 'python', 'python.exe'),
        os.path.join(base_dir, '.venv', 'Scripts', 'python.exe'),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    base_py = os.path.join(getattr(sys, 'base_prefix', sys.prefix), 'python.exe')
    if os.path.isfile(base_py):
        return base_py
    return 'python'


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def calculate_judge_workers(cpu_count=None, cap=None):
    """Default to one worker per logical CPU; cap is an optional operator bound."""
    cpu = max(1, _safe_int(cpu_count, os.cpu_count() or 1))
    if cap is None:
        return cpu
    worker_cap = max(1, _safe_int(cap, cpu))
    return min(cpu, worker_cap)


def judge_worker_limits(cpu_count=None, environ=None):
    """Resolve worker count and cap from the host and optional environment overrides."""
    env = os.environ if environ is None else environ
    cpu_workers = calculate_judge_workers(cpu_count)
    worker_cap = max(1, _safe_int(env.get('JUDGE_WORKER_CAP'), cpu_workers))
    max_workers = min(
        max(1, _safe_int(env.get('MAX_JUDGE_WORKERS'), cpu_workers)),
        worker_cap,
    )
    return max_workers, worker_cap


def host_cpu_limit(environ=None):
    """Default to 100% so dispatch is not paused while the host is fully used."""
    env = os.environ if environ is None else environ
    return min(max(1, _safe_int(env.get('JUDGE_HOST_MAX_CPU_PERCENT'), 100)), 100)


class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'data', 'database.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLITE_BUSY_TIMEOUT_MS = max(5000, _safe_int(os.environ.get('SQLITE_BUSY_TIMEOUT_MS'), 30000))

    MAX_JUDGE_WORKERS, JUDGE_WORKER_CAP = judge_worker_limits()
    JUDGE_TIMEOUT = 30000  # milliseconds
    JUDGE_COMPILE_TIMEOUT_MS = 30000
    JUDGE_COMPILE_MEMORY_MB = 512
    JUDGE_TASK_TIMEOUT_MS = 180000  # milliseconds
    JUDGE_TASK_MAX_RETRIES = 2
    JUDGE_QUEUE_MAXSIZE = min(max(1, _safe_int(os.environ.get('JUDGE_QUEUE_MAXSIZE'), 100)), 1000)
    JUDGE_TOTAL_ACTIVE_MAX = min(
        max(1, _safe_int(os.environ.get('JUDGE_TOTAL_ACTIVE_MAX'), 100)),
        1000,
    )
    JUDGE_USER_ACTIVE_MAX = min(
        max(1, _safe_int(os.environ.get('JUDGE_USER_ACTIVE_MAX'), 3)),
        20,
    )
    JUDGE_HOST_MAX_CPU_PERCENT = host_cpu_limit()
    JUDGE_HOST_MIN_AVAILABLE_MEMORY_MB = min(
        max(256, _safe_int(os.environ.get('JUDGE_HOST_MIN_AVAILABLE_MEMORY_MB'), 1024)),
        32768,
    )
    JUDGE_HOST_BACKOFF_MS = min(
        max(100, _safe_int(os.environ.get('JUDGE_HOST_BACKOFF_MS'), 1000)),
        10000,
    )
    # Idle safety-net poll only; new submissions signal the dispatcher directly.
    JUDGE_DISPATCH_POLL_MS = min(
        max(50, _safe_int(os.environ.get('JUDGE_DISPATCH_POLL_MS'), 500)),
        10000,
    )
    PRACTICE_RUN_TIMEOUT_MS = min(
        max(100, _safe_int(os.environ.get('PRACTICE_RUN_TIMEOUT_MS'), 5000)),
        20000,
    )
    PRACTICE_RUN_MAX_CONCURRENCY = min(
        max(1, _safe_int(os.environ.get('PRACTICE_RUN_MAX_CONCURRENCY'), 1)),
        2,
    )
    MAX_TIME_LIMIT_MS = 20000
    MAX_MEMORY_LIMIT_MB = min(
        max(1, _safe_int(os.environ.get('MAX_MEMORY_LIMIT_MB'), 512)),
        2048,
    )
    MAX_OUTPUT_SIZE = min(
        max(1, _safe_int(os.environ.get('MAX_OUTPUT_SIZE'), 64 * 1024)),
        4 * 1024 * 1024,
    )
    JUDGE_REQUIRE_SANDBOX = os.environ.get('JUDGE_REQUIRE_SANDBOX', '1') != '0'
    JUDGE_LOG_DIR = os.path.join(BASE_DIR, 'data', 'judge_logs')
    # Shown in the header and page titles; chosen in the first-run wizard so a
    # school can label its own instance.
    SITE_NAME = (os.environ.get('EASYOJ_SITE_NAME') or 'EasyOJ').strip()[:60] or 'EasyOJ'

    # Hot database backups. A classroom host rarely has an external scheduler, so
    # the service backs itself up: once at start-up, then once per interval.
    BACKUP_ENABLED = os.environ.get('BACKUP_ENABLED', '1') != '0'
    BACKUP_DIR = os.path.join(BASE_DIR, 'data', 'backups')
    BACKUP_KEEP = min(max(1, _safe_int(os.environ.get('BACKUP_KEEP'), 14)), 365)
    BACKUP_INTERVAL_SECONDS = min(
        max(600, _safe_int(os.environ.get('BACKUP_INTERVAL_SECONDS'), 24 * 3600)),
        30 * 24 * 3600,
    )

    # Test data is administrator-controlled, but still needs hard bounds on a
    # daily-use classroom machine.  Values can be lowered through .env.
    TESTCASE_MAX_INPUT_BYTES = min(
        max(1, _safe_int(os.environ.get('TESTCASE_MAX_INPUT_BYTES'), 4 * 1024 * 1024)),
        64 * 1024 * 1024,
    )
    TESTCASE_MAX_OUTPUT_BYTES = min(
        max(1, _safe_int(os.environ.get('TESTCASE_MAX_OUTPUT_BYTES'), 4 * 1024 * 1024)),
        64 * 1024 * 1024,
    )
    # A testcase upload posts one .in/.out pair, so the request cap has to clear
    # both limits plus multipart framing. It used to default to 256 KB, which
    # rejected any upload the testcase limits actually allowed: Flask aborts with
    # 413 before the view runs, so the 4 MB limits were unreachable and the
    # chunked-write path could never be exercised.
    _UPLOAD_ENVELOPE_BYTES = TESTCASE_MAX_INPUT_BYTES + TESTCASE_MAX_OUTPUT_BYTES + 64 * 1024
    MAX_CONTENT_LENGTH = min(
        max(
            64 * 1024,
            _safe_int(os.environ.get('MAX_CONTENT_LENGTH'), _UPLOAD_ENVELOPE_BYTES),
            _UPLOAD_ENVELOPE_BYTES,
        ),
        256 * 1024 * 1024,
    )
    TESTCASE_MAX_COUNT = min(
        max(1, _safe_int(os.environ.get('TESTCASE_MAX_COUNT'), 2000)),
        10000,
    )
    TESTCASE_MAX_PROBLEM_BYTES = min(
        max(1, _safe_int(os.environ.get('TESTCASE_MAX_PROBLEM_BYTES'), 64 * 1024 * 1024)),
        1024 * 1024 * 1024,
    )
    TESTCASE_MAX_GLOBAL_BYTES = min(
        max(1, _safe_int(os.environ.get('TESTCASE_MAX_GLOBAL_BYTES'), 512 * 1024 * 1024)),
        4 * 1024 * 1024 * 1024,
    )
    TESTCASE_MIN_FREE_SPACE_BYTES = min(
        max(0, _safe_int(os.environ.get('TESTCASE_MIN_FREE_SPACE_BYTES'), 128 * 1024 * 1024)),
        16 * 1024 * 1024 * 1024,
    )
    TESTCASE_UPLOAD_CHUNK_BYTES = min(
        max(4096, _safe_int(os.environ.get('TESTCASE_UPLOAD_CHUNK_BYTES'), 64 * 1024)),
        1024 * 1024,
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
    LOGIN_MAX_FAILURES = max(1, _safe_int(os.environ.get('LOGIN_MAX_FAILURES'), 5))
    LOGIN_LOCKOUT_SECONDS = max(1, _safe_int(os.environ.get('LOGIN_LOCKOUT_SECONDS'), 60))
    LOGIN_FAILURE_WINDOW_SECONDS = max(
        LOGIN_LOCKOUT_SECONDS,
        _safe_int(os.environ.get('LOGIN_FAILURE_WINDOW_SECONDS'), 300),
    )
    LOGIN_RATE_MAX_ENTRIES = max(100, _safe_int(os.environ.get('LOGIN_RATE_MAX_ENTRIES'), 10000))
    SUBMISSION_RATE_MAX = max(1, _safe_int(os.environ.get('SUBMISSION_RATE_MAX'), 30))
    SUBMISSION_RATE_WINDOW_SECONDS = max(
        1,
        _safe_int(os.environ.get('SUBMISSION_RATE_WINDOW_SECONDS'), 60),
    )
    SUBMISSION_RATE_MAX_ENTRIES = max(
        100,
        _safe_int(os.environ.get('SUBMISSION_RATE_MAX_ENTRIES'), 10000),
    )

    SANDBOX_ENABLED = os.environ.get('SANDBOX_ENABLED', '1') != '0'
    SANDBOX_APP_CONTAINER = os.environ.get('SANDBOX_APP_CONTAINER', '1') != '0'
    SANDBOX_STRICT_APP_CONTAINER = os.environ.get('SANDBOX_STRICT_APP_CONTAINER', '1') != '0'
    SANDBOX_PROFILE_NAME = os.environ.get('SANDBOX_PROFILE_NAME', 'EasyOJ.Sandbox')
    SANDBOX_MAX_PROCESSES = _safe_int(os.environ.get('SANDBOX_MAX_PROCESSES'), 8)
    SANDBOX_MAX_WORKSPACE_BYTES = min(
        max(1, _safe_int(os.environ.get('SANDBOX_MAX_WORKSPACE_BYTES'), 64 * 1024 * 1024)),
        512 * 1024 * 1024,
    )
    SANDBOX_MAX_WORKSPACE_FILES = min(
        max(1, _safe_int(os.environ.get('SANDBOX_MAX_WORKSPACE_FILES'), 1024)),
        10000,
    )
    JUDGE_RESERVED_MEMORY_BUDGET_MB = min(
        max(
            MAX_MEMORY_LIMIT_MB,
            _safe_int(
                os.environ.get('JUDGE_RESERVED_MEMORY_BUDGET_MB'),
                MAX_MEMORY_LIMIT_MB * MAX_JUDGE_WORKERS,
            ),
        ),
        16384,
    )
    JUDGE_RESERVED_PROCESS_BUDGET = min(
        max(
            SANDBOX_MAX_PROCESSES,
            _safe_int(
                os.environ.get('JUDGE_RESERVED_PROCESS_BUDGET'),
                SANDBOX_MAX_PROCESSES * MAX_JUDGE_WORKERS,
            ),
        ),
        256,
    )

    SUPPORTED_LANGUAGES = {
        'cpp': {
            'name': 'C++',
            'file_ext': '.cpp',
            'source_file': 'main.cpp',
            'compiler_key': 'g++',
            'compile_args': ['{source}', '-o', '{output}', '-O2', '-std=c++17'],
            'output_name': 'main.exe',
            'run_args': ['{executable}'],
        },
        'java': {
            'name': 'Java',
            'file_ext': '.java',
            'source_file': 'Main.java',
            'compiler_key': 'javac',
            'compile_args': ['{source}'],
            'run_tool_key': 'java',
            'run_args': ['{runtime}', '-cp', '{classpath}', 'Main'],
        },
        'python': {
            'name': 'Python',
            'file_ext': '.py',
            'source_file': 'main.py',
            'interpreter_key': 'python',
            'compile_args': None,
            'run_args': ['{interpreter}', '{source}'],
        },
    }

    _JDK_BIN = _find_jdk_bin(BASE_DIR)
    COMPILER_PATHS = {
        'g++': os.path.join(BASE_DIR, 'toolchain', 'mingw64', 'bin', 'g++.exe'),
        'javac': os.path.join(_JDK_BIN, 'javac.exe'),
        'java': os.path.join(_JDK_BIN, 'java.exe'),
        'python': _find_python_exe(BASE_DIR),
    }


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False

    @classmethod
    def init_app(cls, app):
        secret = (os.environ.get('SECRET_KEY') or '').strip()
        if len(secret) < 32 or secret.lower() in {
            'change-me-to-a-random-string',
            'change-me',
        }:
            raise RuntimeError(
                'SECRET_KEY must be a private random value of at least 32 characters in production. '
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    MAX_JUDGE_WORKERS = 1
    JUDGE_WORKER_CAP = 2
    SANDBOX_ENABLED = False
    JUDGE_REQUIRE_SANDBOX = False
    SANDBOX_STRICT_APP_CONTAINER = False
    JUDGE_HOST_MAX_CPU_PERCENT = 100
    JUDGE_HOST_MIN_AVAILABLE_MEMORY_MB = 1
    # Tests must not spawn a background backup thread or write backup files.
    BACKUP_ENABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    # 'default' points at production so an unnamed configuration can never hand
    # out DEBUG=True. Development has to be asked for by name.
    'default': ProductionConfig,
}
