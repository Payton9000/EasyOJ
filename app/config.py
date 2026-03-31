import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


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
    repo_root = os.path.abspath(os.path.join(base_dir, '..'))
    candidates = [
        os.path.join(repo_root, '.venv', 'Scripts', 'python.exe'),
        os.path.join(base_dir, 'toolchain', 'python', 'python.exe'),
        r'C:\Python311\python.exe',
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return 'python'


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _auto_judge_workers():
    # Reserve one core for web/db/OS to keep the service responsive.
    cpu = os.cpu_count() or 2
    return max(1, cpu - 1)


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'data', 'database.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAX_JUDGE_WORKERS = _safe_int(os.environ.get('MAX_JUDGE_WORKERS'), _auto_judge_workers())
    JUDGE_TIMEOUT = 30000  # milliseconds
    JUDGE_TASK_TIMEOUT_MS = 180000  # milliseconds
    JUDGE_TASK_MAX_RETRIES = 2
    JUDGE_QUEUE_MAXSIZE = 200
    MAX_TIME_LIMIT_MS = 20000
    MAX_MEMORY_LIMIT_MB = 512
    MAX_OUTPUT_SIZE = 64 * 1024  # bytes (64KB)
    JUDGE_LOG_DIR = os.path.join(BASE_DIR, 'data', 'judge_logs')

    SUPPORTED_LANGUAGES = {
        'cpp': {
            'name': 'C++',
            'compile_cmd': '{compiler} {source} -o {output} -O2 -std=c++17',
            'run_cmd': '{executable}',
            'file_ext': '.cpp',
        },
        'java': {
            'name': 'Java',
            'compile_cmd': '{compiler} {source}',
            'run_cmd': 'java -cp {classpath} Main',
            'file_ext': '.java',
        },
        'python': {
            'name': 'Python',
            'compile_cmd': None,
            'run_cmd': '{interpreter} {source}',
            'file_ext': '.py',
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
        if not os.environ.get('SECRET_KEY'):
            import warnings
            warnings.warn('SECRET_KEY not set via environment variable in production!', RuntimeWarning)


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    MAX_JUDGE_WORKERS = 1


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
