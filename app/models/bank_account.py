from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from ..db.base_class import Base

class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    bank_name = Column(String, nullable=False)
    account_number = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    bank_code = Column(String, nullable=False)
    recipient_code = Column(String, unique=True, index=True, nullable=True)

    user = relationship("User", back_populates="bank_accounts")
    withdrawal_requests = relationship("WithdrawalRequest", back_populates="bank_account")
