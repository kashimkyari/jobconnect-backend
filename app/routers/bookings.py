from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.booking_service import BookingService
from app.models.user import User
from app.models.enums import BookingStatus
from app.schemas.booking import (
    BookingCreate, 
    BookingUpdate, 
    BookingResponse, 
    BookingListResponse
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _attach_completion_state(booking):
    """Attach completion flags used by mobile button-state logic."""
    worker_completed, employer_completed = BookingService._get_completion_flags(booking)
    booking.worker_completed = worker_completed
    booking.employer_completed = employer_completed
    booking.completion_state = BookingService._completion_state(worker_completed, employer_completed)
    return booking

def _resolve_status_filter(status_filter: Optional[BookingStatus]) -> Optional[list[BookingStatus]]:
    if not status_filter:
        return None
    if status_filter == BookingStatus.PENDING:
        return [BookingStatus.PENDING, BookingStatus.BOOKED]
    if status_filter == BookingStatus.ACCEPTED:
        return [
            BookingStatus.ACCEPTED,
            BookingStatus.CONFIRMED,
            BookingStatus.EN_ROUTE,
            BookingStatus.ARRIVED,
            BookingStatus.IN_PROGRESS,
            BookingStatus.DONE,
        ]
    return [status_filter]

@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    booking_data: BookingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new booking request for a service.
    Only employers can create bookings.
    """
    if current_user.role.value != "employer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only employers can create bookings"
        )
    
    booking = await BookingService.create_booking(
        db=db,
        booking_data=booking_data,
        employer_id=current_user.id
    )
    return _attach_completion_state(booking)

@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch details of a specific booking"""
    booking = await BookingService.get_booking(db, booking_id)
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Verify user has access to this booking
    if current_user.id not in [booking.employer_id, booking.worker_id]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to view this booking"
        )
    
    return _attach_completion_state(booking)

@router.get("/check-existing/{service_id}")
async def check_existing_booking(
    service_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check if employer has an existing pending or accepted booking for a service"""
    if current_user.role.value != "employer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only employers can check bookings"
        )
    
    booking = await BookingService.get_existing_booking(
        db=db,
        service_id=service_id,
        employer_id=current_user.id
    )
    
    if not booking:
        return {
            "exists": False,
            "message": "No existing booking found",
            "booking": None
        }
    
    return {
        "exists": True,
        "message": "Existing booking found",
            "booking": _attach_completion_state(booking)
    }

@router.get("/my-requests/sent", response_model=BookingListResponse)
async def get_my_sent_bookings(
    skip: int = 0,
    limit: int = 20,
    status_filter: Optional[BookingStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch all bookings sent by the current employer"""
    if current_user.role.value != "employer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only employers can view sent bookings"
        )
    
    statuses = _resolve_status_filter(status_filter)
    bookings, total = await BookingService.get_employer_bookings(
        db=db,
        employer_id=current_user.id,
        skip=skip,
        limit=limit,
        status=status_filter if not statuses else None,
        statuses=statuses
    )
    
    return BookingListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[_attach_completion_state(b) for b in bookings]
    )

@router.get("/my-pending/received", response_model=BookingListResponse)
async def get_my_pending_bookings(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch all pending bookings received by the current worker"""
    if current_user.role.value != "worker":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workers can view pending bookings"
        )
    
    bookings, total = await BookingService.get_worker_bookings(
        db=db,
        worker_id=current_user.id,
        skip=skip,
        limit=limit,
        statuses=[BookingStatus.PENDING, BookingStatus.BOOKED]
    )
    
    return BookingListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[_attach_completion_state(b) for b in bookings]
    )

@router.get("/my-history/all", response_model=BookingListResponse)
async def get_my_booking_history(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch all bookings for the current user (worker or employer)"""
    if current_user.role.value == "worker":
        bookings, total = await BookingService.get_worker_bookings(
            db=db,
            worker_id=current_user.id,
            skip=skip,
            limit=limit
        )
    elif current_user.role.value == "employer":
        bookings, total = await BookingService.get_employer_bookings(
            db=db,
            employer_id=current_user.id,
            skip=skip,
            limit=limit
        )
    else:
        raise HTTPException(status_code=403, detail="Invalid user role")
    
    return BookingListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[_attach_completion_state(b) for b in bookings]
    )

@router.patch("/{booking_id}/accept", response_model=BookingResponse)
async def accept_booking(
    booking_id: int,
    update_data: BookingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Worker accepts a booking request"""
    if current_user.role.value != "worker":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workers can accept bookings"
        )
    
    booking = await BookingService.accept_booking(
        db=db,
        booking_id=booking_id,
        worker_id=current_user.id,
        worker_notes=update_data.worker_notes
    )
    
    return _attach_completion_state(booking)

@router.patch("/{booking_id}/reject", response_model=BookingResponse)
async def reject_booking(
    booking_id: int,
    update_data: BookingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Worker rejects a booking request"""
    if current_user.role.value != "worker":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workers can reject bookings"
        )
    
    booking = await BookingService.reject_booking(
        db=db,
        booking_id=booking_id,
        worker_id=current_user.id,
        worker_notes=update_data.worker_notes
    )
    
    return _attach_completion_state(booking)

@router.patch("/{booking_id}/progress", response_model=BookingResponse)
async def update_booking_progress(
    booking_id: int,
    update_data: BookingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Worker updates booking progress"""
    if current_user.role.value != "worker":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workers can update booking progress"
        )

    booking = await BookingService.update_progress(
        db=db,
        booking_id=booking_id,
        worker_id=current_user.id,
        status=update_data.status,
        worker_notes=update_data.worker_notes
    )

    return _attach_completion_state(booking)

@router.patch("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Employer cancels a pending or accepted booking"""
    if current_user.role.value != "employer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only employers can cancel bookings"
        )
    
    booking = await BookingService.cancel_booking(
        db=db,
        booking_id=booking_id,
        employer_id=current_user.id
    )
    
    return _attach_completion_state(booking)

@router.patch("/{booking_id}/complete", response_model=BookingResponse)
async def complete_booking(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Employer or worker marks a booking as completed (both must confirm)."""
    if current_user.role.value not in ["worker", "employer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workers and employers can complete bookings"
        )
    
    booking = await BookingService.complete_booking(
        db=db,
        booking_id=booking_id,
        user_id=current_user.id
    )
    
    return _attach_completion_state(booking)
