from app.config import settings

def generate_file_url(file_path: str) -> str:
    """
    Generates an absolute URL for a given file path.
    """
    if not file_path:
        return ""
    if file_path.startswith("http://") or file_path.startswith("https://"):
        return file_path
    return f"{settings.API_BASE_URL}{file_path}"
