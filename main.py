from fastapi import FastAPI
from database import get_db
from subscription.routers.plans import plan_router
from subscription.routers.tenants import tenant_router
from subscription.routers.subscriptions import subscription_router
from subscription.routers.payment import payment_router
from subscription.services.subscription_expiry_runs import SubscriptionExpiryRunsService
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    expiry_service = SubscriptionExpiryRunsService()
    scheduler = expiry_service.start_scheduler()
    print("started")
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
app.include_router(plan_router)
app.include_router(tenant_router)
app.include_router(subscription_router)
app.include_router(payment_router)