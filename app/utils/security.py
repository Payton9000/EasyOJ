import logging
import re

logger = logging.getLogger(__name__)

DANGEROUS_PATTERNS = {
    'python': [r'os\.system', r'subprocess', r'\beval\b', r'\bexec\b', r'\bcompile\b'],
    'cpp': [r'system\s*\(', r'fork\s*\(', r'exec\w*\s*\('],
    'java': [r'Runtime\b.*\.exec', r'ProcessBuilder'],
}


def sanitize_code(code, language=None):
    if len(code) > 64 * 1024:
        raise ValueError('Code exceeds 64KB limit')
    languages = [language] if language else list(DANGEROUS_PATTERNS.keys())
    for lang in languages:
        patterns = DANGEROUS_PATTERNS.get(lang, [])
        for pattern in patterns:
            if re.search(pattern, code):
                logger.warning('Dangerous pattern blocked (%s): %s', lang, pattern)
                raise ValueError(
                    f'Code contains a potentially dangerous pattern ({lang}): {pattern}'
                )
    return code
