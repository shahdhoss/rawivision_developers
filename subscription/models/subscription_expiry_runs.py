from database import Base
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import uuid
from sqlalchemy import DateTime
from sqlalchemy.sql import func

class SubscriptionExpiryRuns(Base):
    __tablename__ = "subscription_expiry_runs"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
