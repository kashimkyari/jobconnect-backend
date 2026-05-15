"""
Job State Machine Service - Centralized job lifecycle and state management

This service provides a single source of truth for:
- Job status transitions
- Validation rules for each status
- Available actions based on current state and user role
- State transition enforcement
"""
from typing import List, Tuple, Dict, Optional
from enum import Enum
from app.models.job import JobStatus, CompletionStage
from sqlalchemy.orm import Session


class JobRole(str, Enum):
    """Role context for job operations"""
    EMPLOYER = "employer"
    WORKER = "worker"


# Valid state transitions: from_status -> [to_statuses]
VALID_TRANSITIONS = {
    JobStatus.DRAFT: [JobStatus.OPEN],
    JobStatus.OPEN: [JobStatus.DRAFT, JobStatus.IN_PROGRESS],
    JobStatus.IN_PROGRESS: [JobStatus.COMPLETED],
    JobStatus.COMPLETED: [],  # Terminal state
}

# Actions available at each status for each role
AVAILABLE_ACTIONS = {
    JobStatus.DRAFT: {
        JobRole.EMPLOYER: ["edit", "publish", "delete"],
        JobRole.WORKER: [],
    },
    JobStatus.OPEN: {
        JobRole.EMPLOYER: ["unpublish", "view_applicants", "hire"],
        JobRole.WORKER: ["apply", "view"],
    },
    JobStatus.IN_PROGRESS: {
        JobRole.EMPLOYER: ["view", "approve_completion", "view_progress"],
        JobRole.WORKER: ["view", "mark_complete", "view_progress"],
    },
    JobStatus.COMPLETED: {
        JobRole.EMPLOYER: ["view", "leave_review"],
        JobRole.WORKER: ["view", "leave_review"],
    },
}


class JobStateMachineError(Exception):
    """Base exception for state machine violations"""
    pass


class InvalidStatusTransitionError(JobStateMachineError):
    """Raised when attempting invalid status transition"""
    pass


class InvalidActionError(JobStateMachineError):
    """Raised when action not available in current state"""
    pass


class UnauthorizedActionError(JobStateMachineError):
    """Raised when user role is not allowed to perform action"""
    pass


class JobStateMachine:
    """
    Centralized state machine for job lifecycle management.
    
    Encapsulates all business logic for job status transitions and validates
    state changes against role-based permissions and completion stages.
    """

    @staticmethod
    def can_transition_to(
        current_status: JobStatus,
        target_status: JobStatus,
    ) -> bool:
        """
        Check if a status transition is valid.
        
        Args:
            current_status: Current job status
            target_status: Desired job status
            
        Returns:
            True if transition is allowed, False otherwise
            
        Raises:
            InvalidStatusTransitionError: If transition is invalid
        """
        if target_status not in VALID_TRANSITIONS.get(current_status, []):
            raise InvalidStatusTransitionError(
                f"Cannot transition from {current_status.value} to {target_status.value}"
            )
        return True

    @staticmethod
    def get_available_actions(
        status: JobStatus,
        role: JobRole,
    ) -> List[str]:
        """
        Get all actions available for a role at a given status.
        
        Args:
            status: Current job status
            role: User role (EMPLOYER or WORKER)
            
        Returns:
            List of available action names
        """
        return AVAILABLE_ACTIONS.get(status, {}).get(role, [])

    @staticmethod
    def can_perform_action(
        status: JobStatus,
        role: JobRole,
        action: str,
    ) -> bool:
        """
        Check if a specific action is available for a role at a given status.
        
        Args:
            status: Current job status
            role: User role
            action: Action to perform
            
        Returns:
            True if action is available
            
        Raises:
            UnauthorizedActionError: If action not available for role/status
        """
        available = JobStateMachine.get_available_actions(status, role)
        if action not in available:
            raise UnauthorizedActionError(
                f"Action '{action}' not available for {role.value} when job is {status.value}. "
                f"Available actions: {', '.join(available)}"
            )
        return True

    @staticmethod
    def get_next_completion_stage(
        current_stage: CompletionStage,
        marked_by_role: JobRole,
    ) -> CompletionStage:
        """
        Determine next completion stage based on who marked it complete.
        
        Completion is a two-phase process:
        1. Worker marks complete -> AWAITING_PAYMENT
        2. Payment processed -> PAID
        3. Employer approves -> confirmation
        
        Args:
            current_stage: Current completion stage
            marked_by_role: Role marking the job complete
            
        Returns:
            Next completion stage
        """
        if current_stage == CompletionStage.NOT_STARTED:
            if marked_by_role == JobRole.WORKER:
                return CompletionStage.AWAITING_PAYMENT
            else:
                # Employer can't initiate completion
                raise InvalidActionError(
                    "Only worker can initiate job completion"
                )
        
        if current_stage == CompletionStage.AWAITING_PAYMENT:
            # Payment processing happens atomically
            return CompletionStage.PAID
        
        if current_stage == CompletionStage.PAID:
            # Already paid, employer approval is confirmation
            return CompletionStage.PAID
        
        return current_stage

    @staticmethod
    def validate_publication_readiness(job) -> Tuple[bool, Optional[str]]:
        """
        Validate if job is ready to be published.
        
        Args:
            job: Job instance to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if job.status != JobStatus.DRAFT:
            return False, f"Only DRAFT jobs can be published. Current status: {job.status.value}"
        
        if not job.title or not job.description:
            return False, "Job must have title and description"
        
        if not job.payment_type:
            return False, "Job must have payment_type specified"
        
        if job.payment_type.value == "fixed_price" and (not job.job_price or job.job_price <= 0):
            return False, "Fixed price jobs must have job_price > 0"
        
        if job.payment_type.value == "hourly_rate" and (
            not job.hourly_rate or job.hourly_rate <= 0 or 
            not job.estimated_hours or job.estimated_hours <= 0
        ):
            return False, "Hourly jobs must have hourly_rate > 0 and estimated_hours > 0"
        
        if not job.location_type:
            return False, "Job must have location_type specified"
        
        return True, None

    @staticmethod
    def validate_hiring_readiness(job, application) -> Tuple[bool, Optional[str]]:
        """
        Validate if job and application are ready for hiring.
        
        Args:
            job: Job instance
            application: JobApplication instance
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if job.status != JobStatus.OPEN:
            return False, f"Can only hire for OPEN jobs. Job status: {job.status.value}"
        
        if job.worker_id is not None:
            return False, "Job already has an assigned worker"
        
        return True, None

    @staticmethod
    def validate_completion_readiness(
        job,
        marked_by_role: JobRole,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if job is ready to be marked complete.
        
        Args:
            job: Job instance
            marked_by_role: Role marking job complete
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if job.status != JobStatus.IN_PROGRESS:
            return False, f"Only IN_PROGRESS jobs can be completed. Job status: {job.status.value}"
        
        if marked_by_role == JobRole.WORKER:
            if job.worker_completed:
                return False, "Worker has already marked this job complete"
            if not job.worker_id:
                return False, "No worker assigned to this job"
        
        elif marked_by_role == JobRole.EMPLOYER:
            if job.employer_completed:
                return False, "Employer has already approved completion"
            if not job.completion_stage or job.completion_stage.value != CompletionStage.PAID.value:
                return False, "Employer can only approve after payment is processed"
        
        return True, None

    @staticmethod
    def get_transition_description(from_status: JobStatus, to_status: JobStatus) -> str:
        """
        Get human-readable description of a status transition.
        
        Args:
            from_status: Starting status
            to_status: Target status
            
        Returns:
            Human-readable transition description
        """
        descriptions = {
            (JobStatus.DRAFT, JobStatus.OPEN): "Job published - now visible to workers",
            (JobStatus.OPEN, JobStatus.DRAFT): "Job unpublished - back to draft",
            (JobStatus.OPEN, JobStatus.IN_PROGRESS): "Worker hired - job active",
            (JobStatus.IN_PROGRESS, JobStatus.COMPLETED): "Job completed - payment processed",
        }
        
        key = (from_status, to_status)
        return descriptions.get(key, f"Status changed from {from_status.value} to {to_status.value}")

    @staticmethod
    def get_status_label(status: JobStatus) -> str:
        """
        Get user-friendly label for a status.
        
        Args:
            status: Job status
            
        Returns:
            Human-readable status label
        """
        labels = {
            JobStatus.DRAFT: "Draft",
            JobStatus.OPEN: "Open",
            JobStatus.IN_PROGRESS: "In Progress",
            JobStatus.COMPLETED: "Completed",
        }
        return labels.get(status, status.value.replace("_", " ").title())

    @staticmethod
    def get_completion_stage_label(stage: CompletionStage) -> str:
        """
        Get user-friendly label for a completion stage.
        
        Args:
            stage: Completion stage
            
        Returns:
            Human-readable stage label
        """
        labels = {
            CompletionStage.NOT_STARTED: "Not Started",
            CompletionStage.AWAITING_WORKER: "Awaiting Worker",
            CompletionStage.AWAITING_PAYMENT: "Awaiting Payment",
            CompletionStage.PAID: "Payment Complete",
        }
        return labels.get(stage, stage.value.replace("_", " ").title())
