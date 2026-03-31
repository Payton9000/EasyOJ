import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'data', 'database.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAX_JUDGE_WORKERS = 3
    JUDGE_TIMEOUT = 30000  # milliseconds
    MAX_OUTPUT_SIZE = 64 * 1024  # bytes (64KB)

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

    COMPILER_PATHS = {
        'g++': r'C:\MinGW\bin\g++.exe',
        'javac': r'C:\Program Files\Java\jdk-17\bin\javac.exe',
        'java': r'C:\Program Files\Java\jdk-17\bin\java.exe',
        'python': r'C:\Python311\python.exe',
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
