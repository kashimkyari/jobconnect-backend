from pydantic import BaseModel
from typing import List, Optional

from app.schemas.job import JobInDB as JobSchema
from app.schemas.recent_activity import RecentActivityOut as RecentActivitySchema
from app.schemas.job_application import JobApplicationInDB as JobApplicationSchema
from app.schemas.user import UserOut as UserSchema
from app.models.job_application import ApplicationStatus
from datetime import datetime

class WorkerStats(BaseModel):
    total_applications: int
    active_contracts: int
    total_earnings: float
    completed_jobs: int

class ApplicationWithAction(BaseModel):
    id: int
    job_id: int
    job_title: str
    status: ApplicationStatus
    job_status: str  # DRAFT, OPEN, IN_PROGRESS, COMPLETED
    recommended_action: str
    action_type: str  # boost, follow_up, mark_complete, awaiting_payment, review, none
    boosted: bool
    worker_completed: bool = False  # Whether worker has marked job as complete
    employer_completed: bool = False  # Whether employer has marked job as complete
    priority: int = 0  # 0=low, 1=medium, 2=high (for sorting)

    class Config:
        from_attributes = True

class BoostActivitySchema(BaseModel):
    id: int
    job_title: str
    amount: float
    created_at: datetime

    class Config:
        from_attributes = True

class WorkerDashboardSchema(BaseModel):
    stats: WorkerStats
    recommended_jobs: List[JobSchema]
    applications: List[JobApplicationSchema]
    recent_activity: List[RecentActivitySchema]
    unread_notifications: int
    applications_with_actions: List[ApplicationWithAction]
    boost_activities: List[BoostActivitySchema]

class WorkerHomeScreenSchema(BaseModel):
    user: UserSchema
    dashboard: WorkerDashboardSchema

WorkerDashboardSchema.model_rebuild()
