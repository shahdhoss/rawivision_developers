from fastapi import FastAPI
from database import get_db
from subscription.routers.plans import plan_router
from subscription.routers.tenants import tenant_router
from subscription.routers.subscriptions import subscription_router
from subscription.routers.payment import payment_router

app = FastAPI()
app.include_router(plan_router)
app.include_router(tenant_router)
app.include_router(subscription_router)
app.include_router(payment_router)