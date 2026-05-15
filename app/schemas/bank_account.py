from pydantic import BaseModel
from typing import Optional

class BankAccountBase(BaseModel):
    bank_name: str
    account_number: str
    account_name: str
    bank_code: str

class BankAccountCreate(BankAccountBase):
    pass

class BankAccountInDB(BankAccountBase):
    id: int
    user_id: int
    recipient_code: Optional[str] = None

    class Config:
        from_attributes = True
