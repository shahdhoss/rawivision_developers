from sqlalchemy.ext.asyncio import AsyncSession
from ..models.subscription_expiry_runs import SubscriptionExpiryRuns
from sqlalchemy import select
from datetime import datetime

class SubscriptionExpiryRunsRepository:
    def __init__(self, db:AsyncSession):
        self.db =db
    
    async def create_run(self, last_run_at_date: datetime):
        try:
            new_run = SubscriptionExpiryRuns(last_run_at=last_run_at_date)
            self.db.add(new_run)
            await self.db.commit()
        except Exception as error:
            await self.db.rollback()
            raise error