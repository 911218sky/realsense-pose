from uuid import uuid4


def generate_code() -> str:
    """Generate a stable external identifier (UUID string)."""
    return str(uuid4())


