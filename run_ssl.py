import uvicorn
from app.main import app
from app.config import settings

if __name__ == "__main__":
    if settings.ENABLE_SSL:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            ssl_keyfile=settings.SSL_KEY_PATH,
            ssl_certfile=settings.SSL_CERT_PATH,
        )
    else:
        uvicorn.run(app, host="0.0.0.0", port=8443)
