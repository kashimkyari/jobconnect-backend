import os
import uuid
import aiofiles
import magic
import tempfile
import asyncio
from fastapi import HTTPException, status, UploadFile
from typing import List, Set, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.file import File
from ..config import settings
from ..utils.logging import StructuredLogger
from ..utils.video_compression import VideoCompressor

logger = StructuredLogger("file")

class FileService:
    def __init__(self, db: AsyncSession):
        self.db = db
        
    async def upload_file(
        self,
        file: UploadFile,
        user_id: int,
        category: str,
        allowed_types: Optional[Set[str]] = None,
        max_size: Optional[int] = None,
        reference_id: Optional[int] = None,
        reference_type: Optional[str] = None,
    ) -> File:
        """
        Upload a file with validation and persistence
        
        Args:
            file: The uploaded file
            user_id: ID of the user uploading the file
            category: Category of upload (e.g., 'avatar', 'job_attachment', 'kyc_document')
            allowed_types: Set of allowed mime types
            max_size: Maximum file size in bytes
            reference_id: Optional ID of related entity (e.g., job_id)
            reference_type: Optional type of related entity (e.g., 'job', 'user')
        """
        # Validate file size
        max_size = max_size or settings.MAX_UPLOAD_SIZE
        content = await file.read()
        if len(content) > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds maximum allowed size of {max_size} bytes"
            )

        # Validate file type using python-magic
        file_type = magic.from_buffer(content, mime=True)
        if allowed_types and file_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type {file_type} not allowed. Allowed types: {allowed_types}"
            )

        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1]
        filename = f"{uuid.uuid4()}{file_ext}"
        
        # Ensure base upload directory exists with proper permissions
        try:
            # Use project-relative path if UPLOAD_DIR is not absolute
            base_upload_dir = settings.UPLOAD_DIR
            if not os.path.isabs(base_upload_dir):
                # Get the project root directory (two levels up from this file)
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                base_upload_dir = os.path.join(project_root, settings.UPLOAD_DIR)
            
            # Create base upload dir with proper permissions (755)
            os.makedirs(base_upload_dir, mode=0o755, exist_ok=True)
            
            # Create category subdirectory
            upload_dir = os.path.join(base_upload_dir, category)
            os.makedirs(upload_dir, mode=0o755, exist_ok=True)
            
            # Save file
            file_path = os.path.join(upload_dir, filename)
            async with aiofiles.open(file_path, "wb") as buffer:
                await buffer.write(content)
                
            # Ensure file has correct permissions (644)
            os.chmod(file_path, 0o644)
            
            # Compress video if applicable and category is story_media
            if category == 'story_media' and VideoCompressor.should_compress_video(file_type, len(content)):
                try:
                    logger.info(
                        "Attempting video compression",
                        file_path=file_path,
                        original_size_bytes=len(content)
                    )
                    
                    # Create temp file for compressed video
                    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                        temp_path = tmp.name
                    
                    # Run compression in executor to avoid blocking
                    loop = asyncio.get_event_loop()
                    compression_success = await loop.run_in_executor(
                        None,
                        VideoCompressor.compress_video,
                        file_path,
                        temp_path,
                        'medium',
                        8
                    )
                    
                    if compression_success and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                        # Replace original with compressed version
                        os.remove(file_path)
                        os.rename(temp_path, file_path)
                        os.chmod(file_path, 0o644)
                        
                        # Update content to reflect compressed size
                        async with aiofiles.open(file_path, "rb") as f:
                            content = await f.read()
                        
                        logger.info(
                            "Video compression completed",
                            file_path=file_path,
                            compressed_size_bytes=len(content),
                            original_size_bytes=len(content)
                        )
                    else:
                        # Compression failed, clean up temp file and use original
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        logger.warning(
                            "Video compression failed, using original",
                            file_path=file_path
                        )
                        
                except Exception as e:
                    logger.error(
                        "Error during video compression",
                        error=str(e),
                        file_path=file_path
                    )
                    # Continue with original file if compression fails
            
        except PermissionError as e:
            logger.error(
                "Permission denied while creating upload directory",
                path=upload_dir,
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Upload directory is not writable. Please check server configuration."
            )
        except OSError as e:
            logger.error(
                "Failed to create upload directory or save file",
                path=upload_dir,
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save uploaded file. Please try again."
            )
            
        # Create database record
        db_file = File(
            filename=filename,
            original_filename=file.filename,
            file_path=f"/uploads/{category}/{filename}",
            file_type=file_type,
            file_size=len(content),
            category=category,
            user_id=user_id,
            reference_id=reference_id,
            reference_type=reference_type
        )
        
        self.db.add(db_file)
        await self.db.commit()
        await self.db.refresh(db_file)
        
        logger.info(
            "File uploaded successfully",
            file_id=db_file.id,
            user_id=user_id,
            category=category
        )
        
        return db_file

    async def get_file(self, file_id: int, user_id: Optional[int] = None, is_admin: bool = False) -> Optional[File]:
        """Get file by ID with optional user validation"""
        query = select(File).where(File.id == file_id)
        if user_id and not is_admin:
            query = query.where(File.user_id == user_id)
            
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_files_by_reference(
        self,
        reference_type: str,
        reference_id: int,
        user_id: Optional[int] = None
    ) -> List[File]:
        """Get all files for a specific reference"""
        query = select(File).where(
            File.reference_type == reference_type,
            File.reference_id == reference_id
        )
        
        if user_id:
            query = query.where(File.user_id == user_id)
            
        result = await self.db.execute(query)
        return result.scalars().all()

    async def delete_file(self, file_id: int, user_id: int) -> bool:
        """Delete file and its record"""
        file = await self.get_file(file_id, user_id)
        if not file:
            return False
            
        # Remove physical file
        try:
            # Safely derive on-disk path from stored file_path which is expected
            # to have the form "/uploads/<category>/<filename>". Avoid using
            # str.lstrip which treats its argument as a set of characters.
            stored_path = file.file_path or ""
            prefix = "/uploads/"
            if stored_path.startswith(prefix):
                relative_path = stored_path[len(prefix):]
            else:
                relative_path = stored_path.lstrip("/")

            base_upload_dir = settings.UPLOAD_DIR
            if not os.path.isabs(base_upload_dir):
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                base_upload_dir = os.path.join(project_root, settings.UPLOAD_DIR)

            file_path = os.path.join(base_upload_dir, relative_path)
            if os.path.exists(file_path):
                os.remove(file_path)
            else:
                logger.warn("File not found on disk when attempting delete", file_id=file_id, path=file_path)
        except OSError as e:
            logger.error(
                "Error deleting file",
                file_id=file_id,
                error=str(e)
            )
            
        # Remove database record
        await self.db.delete(file)
        await self.db.commit()
        
        logger.info(
            "File deleted successfully",
            file_id=file_id,
            user_id=user_id
        )
        
        return True

    async def get_user_files(
        self,
        user_id: int,
        category: Optional[str] = None,
        skip: int = 0,
        limit: int = 10
    ) -> List[File]:
        """Get all files uploaded by a user"""
        query = select(File).where(File.user_id == user_id)
        
        if category:
            query = query.where(File.category == category)
            
        query = query.order_by(File.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    @staticmethod
    def get_allowed_types(category: str) -> Set[str]:
        """Get allowed mime types for a category"""
        return {
            "avatar": {"image/jpeg", "image/png", "image/gif"},
            "service_image": {"image/jpeg", "image/png", "image/gif"},
            "job_attachment": {
                "application/pdf",
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "image/jpeg",
                "image/png",
                "text/plain"
            },
            "kyc_document": {"image/jpeg", "image/png", "application/pdf"},
            "profile_document": {"image/jpeg", "image/png", "application/pdf"},
            "message_attachment": {
                "image/jpeg",
                "image/png",
                "image/gif",
                "application/pdf",
                "text/plain"
            },
            "dispute_evidence": {
                "image/jpeg",
                "image/png",
                "image/gif",
                "image/webp",
                "video/mp4",
                "video/quicktime",
                "video/x-msvideo",
                "video/webm"
            }
        }.get(category, set())
