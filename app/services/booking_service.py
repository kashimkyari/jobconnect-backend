from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, desc, select
from datetime import datetime, timedelta
from typing import Optional, List
from decimal import Decimal
from fastapi import HTTPException, status

from app.models.booking import Booking
from app.models.service import Service
from app.models.user import User
from app.models.enums import BookingStatus
from app.models.payment import Payment, PaymentStatus, PaymentType
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.schemas.booking import BookingCreate, BookingUpdate, BookingResponse
from app.services.notification_service import NotificationService
from app.schemas.notification import NotificationCreate
from app.models.notification import NotificationCategory
from app.utils.timezone import now_lagos


class BookingService:
    """Service layer for booking operations"""

    ACTIVE_STATUSES = {
        BookingStatus.PENDING,
        BookingStatus.BOOKED,
        BookingStatus.ACCEPTED,
        BookingStatus.CONFIRMED,
        BookingStatus.EN_ROUTE,
        BookingStatus.ARRIVED,
        BookingStatus.IN_PROGRESS,
        BookingStatus.DONE,
    }

    PROGRESS_STATUSES = [
        BookingStatus.CONFIRMED,
        BookingStatus.EN_ROUTE,
        BookingStatus.ARRIVED,
        BookingStatus.IN_PROGRESS,
        BookingStatus.DONE,
    ]

    PROGRESS_LABELS = {
        BookingStatus.CONFIRMED: "Confirmed",
        BookingStatus.EN_ROUTE: "En route",
        BookingStatus.ARRIVED: "Arrived",
        BookingStatus.IN_PROGRESS: "In progress",
        BookingStatus.DONE: "Done",
    }

    @staticmethod
    def _get_completion_flags(booking: Booking) -> tuple[bool, bool]:
        metadata = booking.booking_metadata or {}
        worker_completed = bool(metadata.get("worker_completed", False))
        employer_completed = bool(metadata.get("employer_completed", False))
        return worker_completed, employer_completed

    @staticmethod
    def _set_completion_flags(booking: Booking, worker_completed: bool, employer_completed: bool) -> None:
        metadata = dict(booking.booking_metadata or {})
        metadata["worker_completed"] = worker_completed
        metadata["employer_completed"] = employer_completed
        booking.booking_metadata = metadata

    @staticmethod
    def _completion_state(worker_completed: bool, employer_completed: bool) -> str:
        if worker_completed and employer_completed:
            return "both_marked_complete"
        if worker_completed:
            return "worker_marked_complete"
        if employer_completed:
            return "employer_marked_complete"
        return "none"

    @staticmethod
    async def create_booking(
        db: AsyncSession,
        booking_data: BookingCreate,
        employer_id: int
    ) -> Booking:
        """
        Create a new booking request from employer to worker.
        Validates that service exists and worker is different from employer.
        Reserves wallet funds in escrow at booking creation.
        """
        # Verify service exists and get worker info
        service_result = await db.execute(
            select(Service).filter(Service.id == booking_data.service_id)
        )
        service = service_result.scalar_one_or_none()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        # Ensure employer is not booking their own service
        if service.worker_id == employer_id:
            raise HTTPException(
                status_code=400,
                detail="You cannot book your own service"
            )

        # Verify employer exists and is active (lock for wallet write)
        employer_result = await db.execute(
            select(User).filter(User.id == employer_id).with_for_update()
        )
        employer = employer_result.scalar_one_or_none()
        if not employer or not employer.is_active:
            raise HTTPException(status_code=404, detail="Employer account not found")

        booking_total = Decimal(str(booking_data.total_price))
        if employer.wallet_balance < booking_total:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"Insufficient funds to book this service. You need ₦{booking_total} "
                    f"but only have ₦{employer.wallet_balance}. Please fund your wallet and try again."
                )
            )

        # Check for existing pending or accepted bookings for this service by this employer
        existing_booking_result = await db.execute(
            select(Booking).filter(
                and_(
                    Booking.service_id == booking_data.service_id,
                    Booking.employer_id == employer_id,
                    Booking.status.in_(list(BookingService.ACTIVE_STATUSES))
                )
            )
        )
        existing_booking = existing_booking_result.scalar_one_or_none()
        if existing_booking:
            raise HTTPException(
                status_code=400,
                detail=f"You already have a pending or accepted booking for this service. Current status: {existing_booking.status.value}"
            )

        # Calculate estimated end date
        start_date = booking_data.start_date
        if booking_data.start_time:
            try:
                start_date = datetime.combine(start_date.date(), booking_data.start_time)
                if booking_data.start_date.tzinfo:
                    start_date = start_date.replace(tzinfo=booking_data.start_date.tzinfo)
            except Exception:
                start_date = booking_data.start_date
        estimated_end_date = start_date + timedelta(hours=booking_data.duration_hours)

        # Create payment record
        payment = Payment(
            user_id=employer_id,
            amount=booking_total,
            currency="NGN",
            payment_type=PaymentType.ESCROW_PAYMENT,
            status=PaymentStatus.HELD,
            description=f"Booking for service: {service.name}"
        )
        db.add(payment)
        await db.flush()  # Get payment ID without committing

        # Create booking
        booking = Booking(
            service_id=booking_data.service_id,
            employer_id=employer_id,
            worker_id=service.worker_id,
            status=BookingStatus.BOOKED,
            start_date=start_date,
            start_time=booking_data.start_time,
            duration_hours=booking_data.duration_hours,
            estimated_end_date=estimated_end_date,
            hourly_rate=booking_data.hourly_rate,
            total_price=booking_data.total_price,
            message=booking_data.message,
            address=booking_data.address,
            latitude=booking_data.latitude,
            longitude=booking_data.longitude,
            payment_id=payment.id,
            payment_status=PaymentStatus.HELD
        )

        db.add(booking)
        await db.flush()

        # Reserve booking amount in escrow immediately
        employer.wallet_balance -= booking_total
        escrow_hold = Transaction(
            user_id=employer.id,
            job_id=None,
            amount=-booking_total,
            status=TransactionStatus.PENDING,
            reference=f"booking_escrow_{booking.id}_hold",
            idempotency_key=f"booking_hold_{booking.id}_{employer.id}",
            description=f"Booking escrow hold for service: {service.name}",
            transaction_type=TransactionType.ESCROW_HOLD.value,
        )
        db.add(escrow_hold)

        BookingService._set_completion_flags(
            booking=booking,
            worker_completed=False,
            employer_completed=False,
        )

        await db.commit()
        await db.refresh(booking)

        # Send notification to worker
        try:
            notification = NotificationCreate(
                user_id=service.worker_id,
                title="New Booking Request",
                message=f"{employer.first_name} wants to book your service '{service.name}' for ₦{booking_data.total_price/1000:.0f}k",
                notification_category=NotificationCategory.BOOKING,
                related_id=booking.id
            )
            notification_service = NotificationService(db)
            await notification_service.create_notification(notification)
        except Exception as e:
            # Log but don't fail if notification fails
            print(f"Failed to send notification: {e}")

        return booking

    @staticmethod
    async def get_booking(db: AsyncSession, booking_id: int) -> Optional[Booking]:
        """Fetch a single booking by ID"""
        result = await db.execute(
            select(Booking).filter(Booking.id == booking_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_employer_bookings(
        db: AsyncSession,
        employer_id: int,
        skip: int = 0,
        limit: int = 20,
        status: Optional[BookingStatus] = None,
        statuses: Optional[List[BookingStatus]] = None
    ) -> tuple[List[Booking], int]:
        """Fetch all bookings created by an employer"""
        query = select(Booking).filter(Booking.employer_id == employer_id)

        if statuses:
            query = query.filter(Booking.status.in_(statuses))
        elif status:
            query = query.filter(Booking.status == status)

        # Get total count
        count_result = await db.execute(
            select(Booking).filter(Booking.employer_id == employer_id)
        )
        total = len(count_result.all())

        # Get paginated results
        result = await db.execute(
            query.order_by(desc(Booking.created_at)).offset(skip).limit(limit)
        )
        bookings = result.scalars().all()

        return bookings, total

    @staticmethod
    async def get_worker_bookings(
        db: AsyncSession,
        worker_id: int,
        skip: int = 0,
        limit: int = 20,
        status: Optional[BookingStatus] = None,
        statuses: Optional[List[BookingStatus]] = None
    ) -> tuple[List[Booking], int]:
        """Fetch all bookings received by a worker"""
        query = select(Booking).filter(Booking.worker_id == worker_id)

        if statuses:
            query = query.filter(Booking.status.in_(statuses))
        elif status:
            query = query.filter(Booking.status == status)

        # Get total count
        count_result = await db.execute(
            select(Booking).filter(Booking.worker_id == worker_id)
        )
        total = len(count_result.all())

        # Get paginated results
        result = await db.execute(
            query.order_by(desc(Booking.created_at)).offset(skip).limit(limit)
        )
        bookings = result.scalars().all()

        return bookings, total

    @staticmethod
    async def accept_booking(
        db: AsyncSession,
        booking_id: int,
        worker_id: int,
        worker_notes: Optional[str] = None
    ) -> Booking:
        """
        Worker accepts a booking.
        Validates that the worker owns this booking and it's still pending.
        Sends notification to employer.
        """
        result = await db.execute(select(Booking).filter(Booking.id == booking_id))
        booking = result.scalar_one_or_none()

        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        if booking.worker_id != worker_id:
            raise HTTPException(
                status_code=403,
                detail="Unauthorized to accept this booking"
            )

        if booking.status in [BookingStatus.ACCEPTED, BookingStatus.CONFIRMED]:
            return booking

        if booking.status not in [BookingStatus.PENDING, BookingStatus.BOOKED]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot accept booking with status: {booking.status.value}"
            )

        # Update booking status
        booking.status = BookingStatus.CONFIRMED
        booking.accepted_at = now_lagos()
        if worker_notes:
            booking.worker_notes = worker_notes

        await db.commit()
        await db.refresh(booking)

        # Send notification to employer
        try:
            worker_result = await db.execute(select(User).filter(User.id == worker_id))
            worker = worker_result.scalar_one_or_none()
            notification = NotificationCreate(
                user_id=booking.employer_id,
                title="Booking Accepted! ✅",
                message=f"{worker.first_name} accepted your booking for ₦{booking.total_price/1000:.0f}k",
                notification_category=NotificationCategory.BOOKING,
                related_id=booking.id
            )
            notification_service = NotificationService(db)
            await notification_service.create_notification(notification)
        except Exception as e:
            print(f"Failed to send acceptance notification: {e}")

        return booking

    @staticmethod
    async def reject_booking(
        db: AsyncSession,
        booking_id: int,
        worker_id: int,
        worker_notes: Optional[str] = None
    ) -> Booking:
        """
        Worker rejects a booking.
        Validates that the worker owns this booking and it's still pending.
        Refunds held funds to employer and sends notification.
        """
        result = await db.execute(
            select(Booking).filter(Booking.id == booking_id).with_for_update(of=Booking)
        )
        booking = result.scalar_one_or_none()

        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        if booking.worker_id != worker_id:
            raise HTTPException(
                status_code=403,
                detail="Unauthorized to reject this booking"
            )

        if booking.status not in [BookingStatus.PENDING, BookingStatus.BOOKED]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reject booking with status: {booking.status.value}"
            )

        # Update booking status
        booking.status = BookingStatus.REJECTED
        booking.rejected_at = now_lagos()
        if worker_notes:
            booking.worker_notes = worker_notes

        hold_result = await db.execute(
            select(Transaction).where(
                Transaction.reference == f"booking_escrow_{booking.id}_hold",
                Transaction.transaction_type == TransactionType.ESCROW_HOLD.value,
                Transaction.status == TransactionStatus.PENDING,
            )
        )
        hold_txn = hold_result.scalar_one_or_none()
        if hold_txn:
            employer_result = await db.execute(
                select(User).where(User.id == booking.employer_id).with_for_update()
            )
            employer = employer_result.scalar_one_or_none()
            if employer:
                refund_amount = abs(hold_txn.amount)
                employer.wallet_balance += refund_amount
                hold_txn.status = TransactionStatus.SUCCESS
                refund_txn = Transaction(
                    user_id=employer.id,
                    job_id=None,
                    amount=refund_amount,
                    status=TransactionStatus.SUCCESS,
                    reference=f"booking_refund_{booking.id}_{int(datetime.utcnow().timestamp())}",
                    related_transaction_id=hold_txn.id,
                    description=f"Booking refund for rejected service booking #{booking.id}",
                    transaction_type=TransactionType.REFUND.value,
                )
                db.add(refund_txn)
                if booking.payment:
                    booking.payment.status = PaymentStatus.REFUNDED
                booking.payment_status = PaymentStatus.REFUNDED

        await db.commit()
        await db.refresh(booking)

        # Send notification to employer
        try:
            worker_result = await db.execute(select(User).filter(User.id == worker_id))
            worker = worker_result.scalar_one_or_none()
            notification = NotificationCreate(
                user_id=booking.employer_id,
                title="Booking Declined ❌",
                message=f"{worker.first_name} declined your booking request",
                notification_category=NotificationCategory.BOOKING,
                related_id=booking.id
            )
            notification_service = NotificationService(db)
            await notification_service.create_notification(notification)
        except Exception as e:
            print(f"Failed to send rejection notification: {e}")

        return booking

    @staticmethod
    async def cancel_booking(
        db: AsyncSession,
        booking_id: int,
        employer_id: int
    ) -> Booking:
        """
        Employer cancels a pending booking and receives escrow refund.
        """
        result = await db.execute(
            select(Booking).filter(Booking.id == booking_id).with_for_update(of=Booking)
        )
        booking = result.scalar_one_or_none()

        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        if booking.employer_id != employer_id:
            raise HTTPException(
                status_code=403,
                detail="Unauthorized to cancel this booking"
            )

        if booking.status in [BookingStatus.REJECTED, BookingStatus.CANCELLED, BookingStatus.COMPLETED]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel booking with status: {booking.status.value}"
            )

        if booking.status not in [
            BookingStatus.PENDING,
            BookingStatus.BOOKED,
            BookingStatus.ACCEPTED,
            BookingStatus.CONFIRMED,
            BookingStatus.EN_ROUTE,
            BookingStatus.ARRIVED,
            BookingStatus.IN_PROGRESS,
        ]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel booking with status: {booking.status.value}"
            )

        # Update booking status
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now_lagos()

        hold_result = await db.execute(
            select(Transaction).where(
                Transaction.reference == f"booking_escrow_{booking.id}_hold",
                Transaction.transaction_type == TransactionType.ESCROW_HOLD.value,
                Transaction.status == TransactionStatus.PENDING,
            )
        )
        hold_txn = hold_result.scalar_one_or_none()
        if hold_txn:
            employer_result = await db.execute(
                select(User).where(User.id == booking.employer_id).with_for_update()
            )
            employer = employer_result.scalar_one_or_none()
            if employer:
                refund_amount = abs(hold_txn.amount)
                employer.wallet_balance += refund_amount
                hold_txn.status = TransactionStatus.SUCCESS
                refund_txn = Transaction(
                    user_id=employer.id,
                    job_id=None,
                    amount=refund_amount,
                    status=TransactionStatus.SUCCESS,
                    reference=f"booking_refund_{booking.id}_{int(datetime.utcnow().timestamp())}",
                    related_transaction_id=hold_txn.id,
                    description=f"Booking refund for cancelled service booking #{booking.id}",
                    transaction_type=TransactionType.REFUND.value,
                )
                db.add(refund_txn)
                if booking.payment:
                    booking.payment.status = PaymentStatus.REFUNDED
                booking.payment_status = PaymentStatus.REFUNDED

        await db.commit()
        await db.refresh(booking)

        return booking

    @staticmethod
    async def complete_booking(
        db: AsyncSession,
        booking_id: int,
        user_id: int
    ) -> Booking:
        """
        Mark a booking as completed.
        Completion is finalized only after both worker and employer confirm.
        Funds transfer to worker is executed when both confirm.
        """
        result = await db.execute(
            select(Booking).filter(Booking.id == booking_id).with_for_update(of=Booking)
        )
        booking = result.scalar_one_or_none()

        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        if booking.status == BookingStatus.COMPLETED:
            return booking

        if booking.status not in [
            BookingStatus.ACCEPTED,
            BookingStatus.CONFIRMED,
            BookingStatus.EN_ROUTE,
            BookingStatus.ARRIVED,
            BookingStatus.IN_PROGRESS,
            BookingStatus.DONE,
        ]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot complete booking with status: {booking.status.value}"
            )

        is_worker = booking.worker_id == user_id
        is_employer = booking.employer_id == user_id
        if not is_worker and not is_employer:
            raise HTTPException(status_code=403, detail="Unauthorized to complete this booking")

        worker_completed, employer_completed = BookingService._get_completion_flags(booking)

        # Idempotent behavior: if this user already marked complete, just return current state.
        if is_worker and worker_completed:
            return booking
        if is_employer and employer_completed:
            return booking

        if is_worker:
            worker_completed = True
        if is_employer:
            employer_completed = True

        BookingService._set_completion_flags(
            booking=booking,
            worker_completed=worker_completed,
            employer_completed=employer_completed,
        )

        if worker_completed and employer_completed:
            existing_release_result = await db.execute(
                select(Transaction).where(
                    Transaction.reference.like(f"booking_payment_{booking.id}_worker_%"),
                    Transaction.transaction_type == TransactionType.ESCROW_RELEASE.value,
                    Transaction.status == TransactionStatus.SUCCESS,
                )
            )
            existing_release = existing_release_result.scalar_one_or_none()

            if not existing_release:
                hold_result = await db.execute(
                    select(Transaction).where(
                        Transaction.reference == f"booking_escrow_{booking.id}_hold",
                        Transaction.transaction_type == TransactionType.ESCROW_HOLD.value,
                        Transaction.status == TransactionStatus.PENDING,
                    )
                )
                hold_txn = hold_result.scalar_one_or_none()
                if not hold_txn:
                    raise HTTPException(
                        status_code=400,
                        detail="Booking escrow not found. Unable to release payment."
                    )

                payout_amount = abs(hold_txn.amount)
                worker_result = await db.execute(
                    select(User).where(User.id == booking.worker_id).with_for_update()
                )
                worker = worker_result.scalar_one_or_none()
                if not worker:
                    raise HTTPException(status_code=404, detail="Worker account not found")

                worker.wallet_balance += payout_amount
                release_txn = Transaction(
                    user_id=worker.id,
                    job_id=None,
                    amount=payout_amount,
                    status=TransactionStatus.SUCCESS,
                    reference=f"booking_payment_{booking.id}_worker_{int(datetime.utcnow().timestamp())}",
                    related_transaction_id=hold_txn.id,
                    description=f"Service booking payout for booking #{booking.id}",
                    transaction_type=TransactionType.ESCROW_RELEASE.value,
                )
                db.add(release_txn)
                hold_txn.status = TransactionStatus.SUCCESS

            booking.status = BookingStatus.COMPLETED
            booking.completed_at = now_lagos()
            booking.payment_status = PaymentStatus.COMPLETED
            if booking.payment:
                booking.payment.status = PaymentStatus.COMPLETED
                booking.payment.completed_at = datetime.utcnow()

        await db.commit()
        await db.refresh(booking)

        return booking

    @staticmethod
    async def get_existing_booking(
        db: AsyncSession,
        service_id: int,
        employer_id: int
    ) -> Optional[Booking]:
        """
        Get existing pending or accepted booking for a service by an employer.
        Returns the booking if it exists, None otherwise.
        """
        result = await db.execute(
            select(Booking).filter(
                and_(
                    Booking.service_id == service_id,
                    Booking.employer_id == employer_id,
                    Booking.status.in_(list(BookingService.ACTIVE_STATUSES))
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_progress(
        db: AsyncSession,
        booking_id: int,
        worker_id: int,
        status: BookingStatus,
        worker_notes: Optional[str] = None
    ) -> Booking:
        """
        Worker updates booking progress (confirmed -> en_route -> arrived -> in_progress -> done).
        Sends a notification to employer on each progress update.
        """
        if status not in BookingService.PROGRESS_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid progress status")

        result = await db.execute(
            select(Booking).filter(Booking.id == booking_id).with_for_update(of=Booking)
        )
        booking = result.scalar_one_or_none()

        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        if booking.worker_id != worker_id:
            raise HTTPException(status_code=403, detail="Unauthorized to update this booking")

        current = booking.status
        allowed_current = [
            BookingStatus.CONFIRMED,
            BookingStatus.ACCEPTED,
            BookingStatus.EN_ROUTE,
            BookingStatus.ARRIVED,
            BookingStatus.IN_PROGRESS,
            BookingStatus.DONE,
        ]
        if current not in allowed_current:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot update booking with status: {current.value}"
            )

        if current == status:
            return booking

        order = {s: i for i, s in enumerate(BookingService.PROGRESS_STATUSES)}
        current_rank = order.get(current, 0)
        next_rank = order.get(status, 0)
        if next_rank < current_rank:
            raise HTTPException(status_code=400, detail="Cannot move booking status backwards")

        booking.status = status
        if worker_notes:
            booking.worker_notes = worker_notes

        await db.commit()
        await db.refresh(booking)

        try:
            worker_result = await db.execute(select(User).filter(User.id == worker_id))
            worker = worker_result.scalar_one_or_none()
            label = BookingService.PROGRESS_LABELS.get(status, status.value.replace('_', ' ').title())
            notification = NotificationCreate(
                user_id=booking.employer_id,
                title="Booking Progress Update",
                message=f"{worker.first_name} updated your booking to: {label}",
                notification_category=NotificationCategory.BOOKING,
                related_id=booking.id
            )
            notification_service = NotificationService(db)
            await notification_service.create_notification(notification)
        except Exception as e:
            print(f"Failed to send progress notification: {e}")

        return booking
