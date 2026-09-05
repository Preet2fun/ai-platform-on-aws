"""Prompt sanitization — strips known injection patterns from user input.

This is a defense-in-depth layer. Combined with the operation allowlist,
even if an injection bypasses this filter, destructive operations are still blocked.
"""

import re

_INJECTION_PATTERNS = [
    r'(?i)(ignore|forget|disregard|override|bypass).{0,30}(previous|above|prior|system|all).{0,30}(instructions|prompt|rules|constraints)',
    r'(?i)you are now\b',
    r'(?i)new (system )?instructions:',
    r'(?i)^system:\s',
    r'(?i)act as if',
    r'(?i)pretend (you are|to be)',
    r'(?i)jailbreak',
    r'(?i)DAN mode',
]

_COMPILED_PATTERNS = [re.compile(p) for p in _INJECTION_PATTERNS]


def sanitize_user_input(text: str, max_length: int = 10000) -> str:
    """Sanitize user input before injecting into agent prompts.
    
    - Strips known prompt injection patterns
    - Caps length to prevent token exhaustion
    - Returns cleaned text (never raises)
    """
    if not text:
        return text
    for pattern in _COMPILED_PATTERNS:
        text = pattern.sub('[FILTERED]', text)
    return text[:max_length]
