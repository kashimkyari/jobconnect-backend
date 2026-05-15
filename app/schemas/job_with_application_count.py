from typing import Optional
from .job import JobInDB
from .review import ReviewInDB


class JobWithApplicationCount(JobInDB):
    application_count: int
    user_review: Optional[ReviewInDB] = None
