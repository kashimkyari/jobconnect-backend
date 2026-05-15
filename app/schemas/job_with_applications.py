from typing import List, Optional

from .job import JobInDB
from .job_application import JobApplicationInDB
from .enums import JobApplicationStatus


class JobWithApplications(JobInDB):
    applications: List[JobApplicationInDB] = []
    application_status: Optional[JobApplicationStatus] = None
    boosted: bool = False

JobWithApplications.model_rebuild()
