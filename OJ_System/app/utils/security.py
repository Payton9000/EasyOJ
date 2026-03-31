import hmac
import logging
import re
import secrets

from flask import session

logger = logging.getLogger(__name__)

DANGEROUS_PATTERNS = {
    'python': [r'os\.system', r'subprocess', r'\bimport\b', r'\beval\b', r'\bexec\b', r'\bcompile\b'],
    'cpp': [r'system\s*\(', r'fork\s*\(', r'exec\w*\s*\('],
    'java': [r'Runtime\.exec', r'ProcessBuilder'],
}


def generate_csrf_token():
    token = secrets.token_hex(32)
    session['_csrf_token'] = token
    return token


def validate_csrf_token(token):
    stored = session.get('_csrf_token', '')
    if not stored or not token:
        return False
    return hmac.compare_digest(stored, token)


def sanitize_code(code):
    if len(code) > 64 * 1024:
        raise ValueError('Code exceeds 64KB limit')
    for lang, patterns in DANGEROUS_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, code):
                logger.warning('Potentially dangerous pattern found (%s): %s', lang, pattern)
    return code


def safe_filename(filename):
    return re.sub(r'[^a-zA-Z0-9._\-]', '_', filename)
