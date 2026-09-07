import logging
import re

logger = logging.getLogger(__name__)

MAX_CODE_BYTES = 64 * 1024

# Secondary screening only: real isolation comes from the AppContainer sandbox and
# Job Object limits. Each entry pairs a pattern with the feature name shown to the
# student, because echoing the regex told them nothing about what to change.
DANGEROUS_PATTERNS = {
    'python': [
        (r'\bos\s*\.\s*system\b', 'os.system'),
        (r'\bsubprocess\b', 'subprocess'),
        (r'\beval\s*\(', 'eval()'),
        (r'\bexec\s*\(', 'exec()'),
    ],
    'cpp': [
        (r'\bsystem\s*\(', 'system()'),
        (r'\bfork\s*\(', 'fork()'),
        # Bounded to the POSIX exec* family so ordinary names like `execute(` pass.
        (r'\bexec(?:l|le|lp|v|ve|vp|vpe)\s*\(', 'exec*()'),
    ],
    'java': [
        (r'Runtime\b[^;]*\.exec', 'Runtime.exec'),
        (r'\bProcessBuilder\b', 'ProcessBuilder'),
    ],
}


class DangerousCodeError(ValueError):
    """Raised when screening rejects a submission; ``feature`` names the trigger."""

    def __init__(self, feature):
        super().__init__(f'Code uses a feature that is not allowed here: {feature}')
        self.feature = feature


def sanitize_code(code, language=None):
    if len(code) > MAX_CODE_BYTES:
        raise ValueError('Code exceeds 64KB limit')
    languages = [language] if language else list(DANGEROUS_PATTERNS.keys())
    for lang in languages:
        for pattern, feature in DANGEROUS_PATTERNS.get(lang, []):
            if re.search(pattern, code):
                logger.warning('Dangerous pattern blocked (%s): %s', lang, feature)
                raise DangerousCodeError(feature)
    return code
