from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from app.models.enums import UserRole

UserRoleEnum = PgEnum(UserRole, name="userrole", create_type=False)
