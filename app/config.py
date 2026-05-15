from pydantic_settings import BaseSettings
from typing import Optional, List
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    READ_REPLICA_DATABASE_URL: Optional[str] = None
    TEST_DATABASE_URL: str
    
    # JWT Settings
    JWT_SECRET_KEY: str
    JWT_REFRESH_SECRET_KEY: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    
    # Paystack
    PAYSTACK_SECRET_KEY: str
    PAYSTACK_PUBLIC_KEY: str
    PAYSTACK_BASE_URL: str
    PAYSTACK_WEBHOOK_SECRET: str
    
    # Frontend URL
    FRONTEND_URL: str
    
    # Email
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_SERVER: str
    MAIL_PORT: int
    MAIL_USE_TLS: bool = True
    MAIL_USE_SSL: bool = False
    MAIL_STARTTLS: bool = True
    MAIL_FROM: str
    MAIL_SENDER_NAME: str
    APP_URL: str = "https://jobconnect.com"
    
    # Twilio
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_FROM_NUMBER: str
    
    # File Upload
    UPLOAD_DIR: str
    MAX_UPLOAD_SIZE: int
    
    # KYC
    UVERIFY_API_KEY: str
    UVERIFY_API_URL: str
    
    # CORS
    ALLOWED_ORIGINS: List[str]
    API_BASE_URL: str
    
    # Rate Limiting
    RATE_LIMITING_ENABLED: bool = False
    RATE_LIMIT_PER_MINUTE: int

    # OTP
    OTP_EXPIRATION_MINUTES: int = 10
    
    # Redis
    REDIS_URL: str

    # NIMC
    NIMC_API_KEY: str
    NIMC_API_URL: str
    
    # App Settings
    COMMISSION_RATE: float = 0.010  # 10%
    PLATFORM_FEE: float = 150.0  # 150 Naira
    DEBUG: bool
    TESTING: bool = False
    API_V1_PREFIX: str
    PROJECT_NAME: str
    VERSION: str
    SYSTEM_USER_ID: int = 1
    DEFAULT_ADMIN_EMAIL: str
    DEFAULT_ADMIN_PASSWORD: str
    
    # SSL
    ENABLE_SSL: bool = False
    SSL_CERT_PATH: Optional[str] = None
    SSL_KEY_PATH: Optional[str] = None
    
    # Stream Chat
    STREAM_CHAT_API_KEY: str
    STREAM_CHAT_API_SECRET: str
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_OAUTH_CREDENTIALS: Optional[str] = None  # JSON string of service account
    
    # Expo Push Notifications
    EXPO_ACCESS_TOKEN: Optional[str] = None
    
    # Liveness Detection & DeepFace
    DEEPFACE_MODEL_HOME: str = "./models/deepface"
    LIVENESS_SESSION_TTL: int = 900  # 15 minutes in seconds
    LIVENESS_JWT_SECRET: str = "deepface_liveness_secret_key_change_in_prod"
    LIVENESS_JWT_EXPIRY_MINUTES: int = 15
    LIVENESS_LOOK_STRAIGHT_YAW_THRESHOLD: float = 15
    LIVENESS_LOOK_STRAIGHT_PITCH_THRESHOLD: float = 10
    LIVENESS_MOVE_HEAD_YAW_LEFT_THRESHOLD: float = -20
    LIVENESS_MOVE_HEAD_YAW_RIGHT_THRESHOLD: float = 20
    LIVENESS_MIN_CONFIDENCE: float = 0.85
    LIVENESS_REQUEST_TIMEOUT: int = 30
    
    REVENUECAT_WEBHOOK_AUTH_TOKEN: str
    SENTRY_AUTH_TOKEN: Optional[str] = None
    SENTRY_DSN: Optional[str] = None
    SENTRY_ENVIRONMENT: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0
    SENTRY_PROFILE_SESSION_SAMPLE_RATE: float = 0.0
    SENTRY_PROFILE_LIFECYCLE: str = "trace"
    SENTRY_ENABLE_LOGS: bool = False



    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
