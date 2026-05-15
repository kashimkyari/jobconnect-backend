from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status
from decimal import Decimal
from typing import List
import uuid

from ..models.transaction import Transaction, TransactionStatus, TransactionType
from ..models.user import User
from ..models.bank_account import BankAccount
from ..utils.logging import payment_logger
from ..config import settings
from .paystack_service import PaystackService

class TransactionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_transaction(
        self,
        user_id: int,
        amount: Decimal,
        transaction_type: str,
        reference: str,
        description: str,
        status: TransactionStatus = TransactionStatus.SUCCESS,
    ) -> Transaction:
        """
        Creates a single transaction and updates the user's wallet balance.
        Amount should be positive for credits and negative for debits.
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        transaction = Transaction(
            user_id=user_id,
            amount=amount,
            status=status,
            reference=reference,
            description=description,
            transaction_type=transaction_type,
        )
        self.db.add(transaction)

        # Update wallet balance
        user.wallet_balance += amount

        await self.db.commit()
        await self.db.refresh(transaction)

        payment_logger.info(
            "Transaction created successfully",
            user_id=user_id,
            amount=str(amount),
            reference=reference,
            new_balance=str(user.wallet_balance),
        )

        return transaction

    async def get_user_transactions(self, user_id: int) -> List[Transaction]:
        """
        Retrieves all transactions for a specific user.
        """
        result = await self.db.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
        )
        return result.scalars().all()

    async def get_transaction_by_reference(self, reference: str) -> Transaction:
        """
        Retrieves a transaction by its reference.
        """
        result = await self.db.execute(
            select(Transaction).where(Transaction.reference == reference)
        )
        return result.scalar_one_or_none()

    async def withdraw_funds(
        self, user_id: int, amount: Decimal, bank_account_id: int = None, bank_code: str = None, account_number: str = None, bank_name: str = None
    ) -> Transaction:
        """
        Initiates a withdrawal to a user's bank account.
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if user.wallet_balance < amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds"
            )

        if bank_account_id:
            bank_account_result = await self.db.execute(
                select(BankAccount).where(
                    BankAccount.id == bank_account_id, BankAccount.user_id == user_id
                )
            )
            bank_account = bank_account_result.scalar_one_or_none()
            if not bank_account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found"
                )
        else:
            bank_account = BankAccount(
                user_id=user_id,
                bank_code=bank_code,
                account_number=account_number,
                bank_name=bank_name,
                account_name="",  # Will be updated after verification
            )
            self.db.add(bank_account)
            await self.db.flush()

        paystack_service = PaystackService()

        if not bank_account.recipient_code:
            verified_account = await paystack_service.verify_account(
                bank_account.account_number, bank_account.bank_code
            )
            recipient_code = await paystack_service.create_transfer_recipient(
                verified_account["account_name"],
                bank_account.account_number,
                bank_account.bank_code,
            )
            bank_account.recipient_code = recipient_code
            self.db.add(bank_account)

        reference = f"wd_{uuid.uuid4()}"
        amount_in_kobo = int(amount * 100)

        transaction = Transaction(
            user_id=user_id,
            amount=-amount,
            status=TransactionStatus.PENDING,
            reference=reference,
            description=f"Withdrawal to {bank_account.bank_name}",
            transaction_type=TransactionType.WITHDRAWAL,
        )
        self.db.add(transaction)
        user.wallet_balance -= amount

        await self.db.commit()
        await self.db.refresh(transaction)

        try:
            await paystack_service.initiate_transfer(
                amount_in_kobo,
                bank_account.recipient_code,
                reference,
                "Funds Withdrawal",
            )
        except HTTPException as e:
            transaction.status = TransactionStatus.FAILED
            user.wallet_balance += amount
            await self.db.commit()
            raise e

        return transaction

    async def update_transaction_status_from_webhook(self, data: dict):
        """
        Updates a transaction's status based on a Paystack webhook.
        """
        reference = data.get("reference")
        if not reference:
            return

        transaction = await self.get_transaction_by_reference(reference)
        if not transaction:
            return

        if data["status"] == "success":
            transaction.status = TransactionStatus.SUCCESS
        elif data["status"] == "failed":
            transaction.status = TransactionStatus.FAILED
            result = await self.db.execute(
                select(User).where(User.id == transaction.user_id).with_for_update()
            )
            user = result.scalar_one_or_none()
            if user:
                user.wallet_balance -= transaction.amount  # amount is negative

        await self.db.commit()
