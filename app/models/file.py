from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, BigInteger, Enum
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base_class import Base
from app.schemas.file import FileCategory

class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)  # UUID-based filename
    original_filename = Column(String, nullable=False)  # Original user filename
    file_path = Column(String, nullable=False)  # Path relative to UPLOAD_DIR
    file_type = Column(String, nullable=False)  # MIME type
    file_size = Column(BigInteger, nullable=False)  # Size in bytes
    category = Column(Enum(FileCategory), nullable=False)  # avatar, job_attachment, etc.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reference_id = Column(Integer, nullable=True)  # ID of related entity
    reference_type = Column(String, nullable=True)  # Type of related entity
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="files")
