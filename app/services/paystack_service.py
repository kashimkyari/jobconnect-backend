import httpx
from fastapi import HTTPException, status
from ..config import settings
from ..utils.logging import payment_logger

class PaystackService:
    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.base_url = "https://api.paystack.co"
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    async def verify_account(self, account_number: str, bank_code: str) -> dict:
        """
        Verifies a bank account number.
        """
        url = f"{self.base_url}/bank/resolve?account_number={account_number}&bank_code={bank_code}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code != 200:
                payment_logger.error(
                    "Paystack account verification failed",
                    response_data=response.json(),
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Could not verify bank account.",
                )
            return response.json()["data"]

    async def create_transfer_recipient(
        self, account_name: str, account_number: str, bank_code: str
    ) -> str:
        """
        Creates a new transfer recipient.
        """
        url = f"{self.base_url}/transferrecipient"
        payload = {
            "type": "nuban",
            "name": account_name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": "NGN",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload)
            if response.status_code != 201:
                payment_logger.error(
                    "Paystack transfer recipient creation failed",
                    response_data=response.json(),
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Could not create transfer recipient.",
                )
            return response.json()["data"]["recipient_code"]

    async def initiate_transfer(
        self, amount: int, recipient_code: str, reference: str, reason: str
    ) -> dict:
        """
        Initiates a transfer to a recipient. Amount should be in kobo.
        """
        url = f"{self.base_url}/transfer"
        payload = {
            "source": "balance",
            "amount": amount,
            "recipient": recipient_code,
            "reference": reference,
            "reason": reason,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload)
            if response.status_code != 200:
                payment_logger.error(
                    "Paystack transfer initiation failed",
                    response_data=response.json(),
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Could not initiate transfer.",
                )
            return response.json()["data"]
