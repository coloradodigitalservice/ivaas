"""Portable validation constraints shared by core DTOs and API adapters.

These values are transport-neutral contract metadata. Applications can use them
to describe their transport schemas without depending on a validation framework.

This allows us to reuse the same validation constraints across different layers of the application
"""

NAME_MIN_LENGTH = 1
NAME_MAX_LENGTH = 256
NAME_PATTERN = r"^[^\x00-\x1F\x7F]+$"
SSN_PATTERN = r"^[0-9]{9}$"
LAST4_SSN_PATTERN = r"^[0-9]{4}$"
