import os
import tempfile
from pathlib import Path
try:
    import ffmpeg
    FFMPEG_AVAILABLE = True
except ImportError:
    FFMPEG_AVAILABLE = False
from ..utils.logging import StructuredLogger

logger = StructuredLogger("video_compression")


class VideoCompressor:
    """
    Handles lossless video compression using FFmpeg.
    Optimizes videos for web delivery while maintaining quality.
    """
    
    # Compression presets: (quality, bitrate_kbps)
    PRESETS = {
        'high': {
            'video_bitrate': '2500k',
            'audio_bitrate': '128k',
            'crf': '18',  # Quality (0-51, lower is better)
        },
        'medium': {
            'video_bitrate': '1500k',
            'audio_bitrate': '96k',
            'crf': '23',
        },
        'low': {
            'video_bitrate': '800k',
            'audio_bitrate': '64k',
            'crf': '28',
        },
    }
    
    @staticmethod
    def compress_video(
        input_path: str,
        output_path: str,
        preset: str = 'medium',
        max_duration: int = 8,
    ) -> bool:
        """
        Compress video file using FFmpeg.
        
        Args:
            input_path: Path to input video file
            output_path: Path to save compressed video
            preset: Compression preset ('high', 'medium', 'low')
            max_duration: Maximum video duration in seconds
            
        Returns:
            True if compression successful, False otherwise
        """
        if not FFMPEG_AVAILABLE:
            logger.warning("FFmpeg not installed, skipping compression")
            return False
        try:
            if preset not in VideoCompressor.PRESETS:
                preset = 'medium'
            
            config = VideoCompressor.PRESETS[preset]
            
            logger.info(
                "Starting video compression",
                input_file=input_path,
                output_file=output_path,
                preset=preset,
                max_duration=max_duration
            )
            
            # Build FFmpeg command
            stream = ffmpeg.input(input_path)
            
            # Limit duration if needed
            if max_duration:
                stream = stream.filter('trim', end=max_duration)
            
            # Apply video compression with H.264 codec
            stream = stream.video.filter('scale', w='trunc(oh*a/2)*2', h='720').filter('fps', fps='24')
            
            # Combine with audio and output
            stream = ffmpeg.concat(stream, stream.audio, v=1, a=1)
            stream = ffmpeg.output(
                stream,
                output_path,
                vcodec='libx264',
                preset='medium',  # FFmpeg preset (ultrafast, fast, medium, slow, veryslow)
                crf=config['crf'],  # Quality factor
                acodec='aac',
                audio_bitrate=config['audio_bitrate'],
                movflags='faststart',  # Optimize for web streaming
            )
            
            # Execute compression with overwrite flag
            ffmpeg.run(stream, overwrite_output=True, quiet=False, capture_stdout=True)
            
            # Check output file exists and has size
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                original_size = os.path.getsize(input_path)
                compressed_size = os.path.getsize(output_path)
                reduction_percent = ((original_size - compressed_size) / original_size) * 100
                
                logger.info(
                    "Video compression successful",
                    original_size_bytes=original_size,
                    compressed_size_bytes=compressed_size,
                    reduction_percent=reduction_percent,
                    preset=preset
                )
                return True
            else:
                logger.error("Compressed video file is empty", output_file=output_path)
                return False
                
        except ffmpeg.Error as e:
            logger.error(
                "FFmpeg compression error",
                error=str(e),
                input_file=input_path,
                stderr=e.stderr.decode() if e.stderr else None
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error during video compression",
                error=str(e),
                input_file=input_path
            )
            return False
    
    @staticmethod
    def should_compress_video(file_type: str, file_size: int) -> bool:
        """
        Determine if video should be compressed based on type and size.
        
        Args:
            file_type: MIME type of file
            file_size: Size of file in bytes
            
        Returns:
            True if compression is recommended and ffmpeg is available
        """
        video_types = {'video/mp4', 'video/quicktime', 'video/x-msvideo'}
        
        # Compress if it's a video, ffmpeg is available, and file is larger than 5MB
        return FFMPEG_AVAILABLE and file_type in video_types and file_size > 5 * 1024 * 1024
