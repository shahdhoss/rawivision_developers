from ..repository.subscription_expiry_runs import SubscriptionExpiryRunsRepository
from ..services.subscriptions import SubscriptionsService
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import atexit
from database import sessionlocal
from ..repository.plans import PlansRepository
from ..repository.subscriptions import SubscriptionsRepository

class SubscriptionExpiryRunsService:
    async def run_expiry_jobs(self):
        try:
            async with sessionlocal() as db:
                repo = SubscriptionExpiryRunsRepository(db)
                plans_repo = PlansRepository(db=db)
                subscription_repo = SubscriptionsRepository(db)
                subscription_service = SubscriptionsService(subscription_repo=subscription_repo, plans_repo=plans_repo)
                subscriptions = await subscription_service.get_all_subscriptions()  
                now = datetime.now(timezone.utc)
                for subscription in subscriptions:
                    if subscription.state == "trial" and subscription.trial_ends_at:
                        if now > subscription.trial_ends_at:
                            await subscription_service.expire(subscription_id=subscription.id)  
                    elif subscription.state == "active" and subscription.billing_cycle_end:
                        if now > subscription.billing_cycle_end:
                            await subscription_service.expire(subscription_id=subscription.id)  
                await repo.create_run(last_run_at_date=now) 
                print("inside the run expiry job")
        except Exception as error:
            print(f"Expiry job failed: {error}")
            raise error
    
    def start_scheduler(self):
        try:
            scheduler = AsyncIOScheduler()
            scheduler.add_job(self.run_expiry_jobs, 'cron', hour=23, minute=59, misfire_grace_time=3600, coalesce=True, timezone=pytz.timezone('Africa/Cairo'))
            scheduler.start()
            print("started scheduler")
            print(datetime.now(pytz.timezone('Africa/Cairo')))
            atexit.register(lambda: scheduler.shutdown())
            return scheduler
        except Exception as error:
            print(f"a problem happened {error}")
            raise error

