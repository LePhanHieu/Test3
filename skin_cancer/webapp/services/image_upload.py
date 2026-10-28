"""Small, reusable guards for request-bound image streams."""


class UploadTooLarge(ValueError):
    """Raised when an upload exceeds its endpoint's byte limit."""


def read_limited_upload(stream, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UploadTooLarge(
            f"Upload exceeds maximum size of {max_bytes} bytes"
        )
    return data
