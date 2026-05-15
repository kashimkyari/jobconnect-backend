from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status
from typing import Dict, Any, Optional
from datetime import datetime
import uuid
import httpx
import asyncio
from decimal import Decimal

from ..models.payment import Payment, PaymentStatus, PaymentType
from ..models.transaction import Transaction, TransactionType
from ..models.user import User
from ..models.notification import NotificationCategory
from ..schemas.payment import PaymentCreate
from ..schemas.notification import NotificationCreate
from ..config import settings
from ..utils.logging import payment_logger
from .notification_service import NotificationService
from .transaction_service import TransactionService
from .security_service import SecurityService
from .referral_service import ReferralService

class PaymentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        if not settings.PAYSTACK_SECRET_KEY:
            raise ValueError("PAYSTACK_SECRET_KEY is not set in the environment variables")
        self.base_url = settings.PAYSTACK_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }

    async def initialize_payment(self, user_id: int, amount: Decimal, currency: str = "NGN"):
        """Initialize a payment for a user to fund their wallet."""
        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        try:
            url = f"{self.base_url}/transaction/initialize"
            payload = {
                "email": user.email,
                "amount": int(amount * 100),  # Convert to kobo
                "currency": currency,
                "metadata": {
                    "user_id": user.id,
                    "purpose": "Wallet Funding"
                }
            }

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                response_data = response.json()

            if not response_data.get('status'):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=response_data.get('message', 'Failed to initialize payment')
                )

            payment = Payment(
                user_id=user.id,
                amount=amount,
                status=PaymentStatus.PENDING,
                paystack_reference=response_data['data']['reference'],
                payment_type=PaymentType.WALLET_FUNDING.value
            )
            self.db.add(payment)
            await self.db.commit()

            payment_logger.info(
                "Payment initiated for wallet funding",
                user_id=user.id,
                amount=str(amount),
                reference=response_data['data']['reference']
            )

            return response_data['data']

        except httpx.HTTPStatusError as e:
            payment_logger.error(
                "Payment initiation API call failed",
                error=str(e),
                response=e.response.text,
                user_id=user.id
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initiate payment"
            )
        except httpx.RequestError as e:
            payment_logger.error(
                "Payment initiation API call failed",
                error=str(e),
                user_id=user.id
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initiate payment"
            )

    async def create_customer(self, email: str, first_name: str, last_name: str, phone: str):
        """Create a customer on Paystack."""
        try:
            url = f"{self.base_url}/customer"
            payload = {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
            }

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                response_data = response.json()

            if not response_data.get('status'):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=response_data.get('message', 'Failed to create customer')
                )

            return response_data['data']

        except httpx.RequestError as e:
            payment_logger.error(
                "Customer creation API call failed",
                error=str(e),
                email=email
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create customer"
            )

    async def verify_payment(self, reference: str):
        """Verify a payment with Paystack."""
        try:
            url = f"{self.base_url}/transaction/verify/{reference}"
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                response_data = response.json()

            if response_data['data']['status'] == 'success':
                query = select(Payment).where(Payment.paystack_reference == reference)
                result = await self.db.execute(query)
                payment = result.scalar_one_or_none()

                if payment and payment.status == PaymentStatus.PENDING:
                    payment.status = PaymentStatus.COMPLETED
                    payment.channel = response_data['data']['channel']
                    payment.ip_address = response_data['data']['ip_address']
                    payment.payment_metadata = response_data['data']

                    transaction_service = TransactionService(self.db)
                    
                    # Credit the full amount
                    await transaction_service.create_transaction(
                        user_id=payment.user_id,
                        amount=payment.amount,
                        transaction_type=TransactionType.WALLET_FUNDING.value,
                        reference=reference,
                        description="Wallet funding via Paystack",
                    )

                    # Deduct platform fee and commission from the main transaction
                    platform_fee = Decimal(settings.PLATFORM_FEE)
                    commission = payment.amount * Decimal(settings.COMMISSION_RATE)
                    
                    # The create_transaction service already adjusts the wallet balance
                    # so we just need to record the fees on the transaction record
                    
                    # Get the wallet funding transaction
                    wallet_funding_txn = await transaction_service.get_transaction_by_reference(reference)
                    
                    if wallet_funding_txn:
                        wallet_funding_txn.platform_fee = platform_fee
                        wallet_funding_txn.commission = commission
                        self.db.add(wallet_funding_txn)
                        
                        # Manually deduct from wallet balance since we are not creating new txns
                        user = await self.db.get(User, payment.user_id)
                        if user:
                            user.wallet_balance -= (platform_fee + commission)
                            self.db.add(user)

                    notification_service = NotificationService(self.db)
                    notification_in = NotificationCreate(
                        user_id=payment.user_id,
                        title="Wallet Funded",
                        message=f"Your wallet has been successfully funded with {payment.amount}.",
                        category=NotificationCategory.PAYMENTS_AND_WALLET,
                        action_screen="TransactionHistory",
                        action_payload={"transaction_id": payment.id}
                    )
                    await notification_service.create_notification(notification_in)

                    # Grant referral commission if applicable
                    referral_service = ReferralService(self.db)
                    await referral_service.grant_transaction_commission(
                        user_id=payment.user_id,
                        transaction_amount=payment.amount,
                        transaction_id=payment.id  # Assuming payment id can be used as a transaction reference
                    )

            return response_data['data']

        except httpx.RequestError as e:
            payment_logger.error(
                "Payment verification API call failed",
                error=str(e),
                reference=reference
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify payment"
            )

    async def initiate_refund(self, payment_id: int) -> Optional[Payment]:
        """
        Initiate a refund for a payment. Creates a refund transaction and
        marks the payment as refunded.
        """
        payment = await self.db.get(Payment, payment_id)
        if not payment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

        if payment.status == PaymentStatus.REFUNDED:
            return None

        refund_amount = Decimal(payment.amount)
        transaction_service = TransactionService(self.db)
        await transaction_service.create_transaction(
            user_id=payment.user_id,
            amount=refund_amount,
            transaction_type=TransactionType.REFUND.value,
            reference=f"refund_{payment.id}_{uuid.uuid4().hex[:8]}",
            description=f"Refund for payment #{payment.id}",
        )

        payment.status = PaymentStatus.REFUNDED
        payment.completed_at = datetime.utcnow()
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)

        return payment

    async def pay_worker_from_wallet(self, employer_id: int, worker_id: int, amount: Decimal, pin: str, otp_code: str = None):
        """Pay a worker from the employer's wallet."""
        employer = await self.db.get(User, employer_id)
        worker = await self.db.get(User, worker_id)

        if not employer or not worker:
            raise HTTPException(status_code=404, detail="User not found")

        if employer.wallet_balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient wallet balance")

        security_service = SecurityService(self.db)
        if not await security_service.verify_transaction_pin(employer_id, pin):
            raise HTTPException(status_code=400, detail="Invalid transaction pin")

        if employer.is_2fa_enabled:
            if not otp_code or not await security_service.verify_2fa(employer_id, otp_code):
                raise HTTPException(status_code=400, detail="Invalid 2FA code")

        transaction_service = TransactionService(self.db)
        
        # Debit employer
        await transaction_service.create_transaction(
            user_id=employer_id,
            amount=amount,
            transaction_type=TransactionType.ESCROW_PAYMENT.value,
            reference=f"wallet_transfer_{employer_id}_{worker_id}",
            description=f"Payment to {worker.first_name} {worker.last_name}",
        )

        # Credit worker, deducting fee if not subscribed
        worker_fee = Decimal(0)
        if not worker.subscription_status:
            worker_fee = amount * Decimal('0.02')
            
        net_amount = amount - worker_fee

        await transaction_service.create_transaction(
            user_id=worker_id,
            amount=net_amount,
            transaction_type=TransactionType.ESCROW_RELEASE.value,
            reference=f"wallet_transfer_{employer_id}_{worker_id}",
            description=f"Payment from {employer.first_name} {employer.last_name}",
        )

        if worker_fee > 0:
            # Get the escrow release transaction
            escrow_release_txn = await transaction_service.get_transaction_by_reference(f"wallet_transfer_{employer_id}_{worker_id}")
            if escrow_release_txn:
                escrow_release_txn.platform_fee = worker_fee
                self.db.add(escrow_release_txn)

                # Manually deduct from wallet balance
                worker.wallet_balance -= worker_fee
                self.db.add(worker)

        payment = Payment(
            user_id=employer_id,
            amount=amount,
            status=PaymentStatus.COMPLETED,
            paystack_reference=f"wallet_transfer_{employer_id}_{worker_id}",
            payment_type=PaymentType.ESCROW_PAYMENT.value
        )
        self.db.add(payment)
        await self.db.commit()

        notification_service = NotificationService(self.db)
        await notification_service.create_notification(NotificationCreate(
            user_id=worker_id,
            title="Payment Received",
            message=f"You have received a payment of {amount} from {employer.first_name}.",
            category=NotificationCategory.PAYMENTS_AND_WALLET,
            action_screen="TransactionHistory",
            action_payload={"transaction_id": payment.id}
        ))
        await notification_service.create_notification(NotificationCreate(
            user_id=employer_id,
            title="Payment Sent",
            message=f"You have sent a payment of {amount} to {worker.first_name}.",
            category=NotificationCategory.PAYMENTS_AND_WALLET,
            action_screen="TransactionHistory",
            action_payload={"transaction_id": payment.id}
        ))

    async def withdraw_funds(self, user_id: int, amount: Decimal, bank_details: Dict[str, Any], pin: str, otp_code: str = None):
        """Withdraw funds from a user's wallet to their bank account."""
        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if user.wallet_balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient wallet balance")

        security_service = SecurityService(self.db)
        if not await security_service.verify_transaction_pin(user_id, pin):
            raise HTTPException(status_code=400, detail="Invalid transaction pin")

        if user.is_2fa_enabled:
            if not otp_code or not await security_service.verify_2fa(user_id, otp_code):
                raise HTTPException(status_code=400, detail="Invalid 2FA code")

        try:
            # Create transfer recipient
            recipient_url = f"{self.base_url}/transferrecipient"
            recipient_payload = {
                "type": "nuban",
                "name": f"{user.first_name} {user.last_name}",
                "account_number": bank_details['account_number'],
                "bank_code": bank_details['bank_code'],
                "currency": "NGN"
            }
            async with httpx.AsyncClient(timeout=30) as client:
                recipient_response = await client.post(recipient_url, headers=self.headers, json=recipient_payload)
                recipient_response.raise_for_status()
                recipient_data = recipient_response.json()

            # Initiate transfer
            transfer_url = f"{self.base_url}/transfer"
            transfer_payload = {
                "source": "balance",
                "amount": int(amount * 100),
                "recipient": recipient_data['data']['recipient_code'],
                "reason": "Wallet Withdrawal"
            }
            async with httpx.AsyncClient(timeout=30) as client:
                transfer_response = await client.post(transfer_url, headers=self.headers, json=transfer_payload)
                transfer_response.raise_for_status()
                transfer_data = transfer_response.json()

            transaction_service = TransactionService(self.db)
            await transaction_service.create_transaction(
                user_id=user_id,
                amount=amount,
                transaction_type=TransactionType.WALLET_WITHDRAWAL.value,
                reference=transfer_data['data']['transfer_code'],
                description="Wallet withdrawal to bank account",
            )
            
            withdrawal = Payment(
                user_id=user_id,
                amount=-amount,
                status=PaymentStatus.PENDING,
                paystack_reference=transfer_data['data']['transfer_code'],
                payment_type=PaymentType.WITHDRAWAL.value
            )
            self.db.add(withdrawal)
            await self.db.commit()

            notification_service = NotificationService(self.db)
            await notification_service.create_notification(NotificationCreate(
                user_id=user_id,
                title="Withdrawal Initiated",
            message=f"Your withdrawal of {amount} is being processed.",
            category=NotificationCategory.PAYMENTS_AND_WALLET,
            action_screen="TransactionHistory",
            action_payload={"transaction_id": withdrawal.id}
        ))

            return transfer_data['data']

        except httpx.RequestError as e:
            payment_logger.error("Withdrawal failed", error=str(e), user_id=user_id)
            raise HTTPException(status_code=500, detail="Failed to process withdrawal")
        except Exception as e:
            payment_logger.error("Withdrawal failed", error=str(e), user_id=user_id)
            raise HTTPException(status_code=500, detail="Failed to process withdrawal")

    async def get_banks(self):
        """Get a list of supported banks from Paystack."""
        try:
            url = f"{self.base_url}/bank"
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()['data']
        except httpx.RequestError as e:
            payment_logger.error("Failed to fetch banks from Paystack", error=str(e))
            raise HTTPException(status_code=500, detail="Could not retrieve bank list.")

    async def resolve_account(self, account_number: str, bank_code: str):
        """
        Resolve a bank account to get the account name.
        Implements retry logic with exponential backoff for rate limiting (429).
        """
        max_retries = 3
        retry_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/bank/resolve?account_number={account_number}&bank_code={bank_code}"
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(url, headers=self.headers)
                    response.raise_for_status()
                    return response.json()['data']
            except httpx.HTTPStatusError as e:
                # Handle rate limiting with retry
                if e.response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                        payment_logger.warning(
                            f"Rate limited by Paystack. Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})",
                            account_number=account_number,
                            bank_code=bank_code
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # All retries exhausted
                        payment_logger.error(
                            "Rate limit exceeded after retries",
                            account_number=account_number,
                            bank_code=bank_code
                        )
                        raise HTTPException(
                            status_code=429,
                            detail="Service temporarily unavailable due to rate limiting. Please try again later."
                        )
                else:
                    # Other HTTP errors
                    payment_logger.error(
                        "Failed to resolve account with Paystack",
                        error=str(e),
                        status_code=e.response.status_code
                    )
                    raise HTTPException(status_code=400, detail="Could not verify account details.")
            except httpx.RequestError as e:
                payment_logger.error("Failed to resolve account with Paystack", error=str(e))
                raise HTTPException(status_code=400, detail="Could not verify account details.")

    async def get_user_transactions(self, user_id: int):
        """Get all transactions for a user."""
        query = select(Transaction).where(Transaction.user_id == user_id).order_by(Transaction.created_at.desc())
        result = await self.db.execute(query)
        return result.scalars().all()
