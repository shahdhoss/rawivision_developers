from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import httpx

from config import Config
from database import get_db
from ..services.subscriptions import SubscriptionsService
from ..services.plans import PlansService
from ..services.tenants import TenantsService
from ..repository.subscriptions import SubscriptionsRepository
from ..repository.plans import PlansRepository
from ..repository.tenants import TenantsRepository
from ..utils.exceptions import SubscriptionNotFound, PlanNotFound, TenantNotFound

payment_router = APIRouter(prefix="/payment", tags=["Payment Integration"])

async def get_subscription_repo(db: AsyncSession = Depends(get_db)):
    return SubscriptionsRepository(db=db)

async def get_plans_repo(db: AsyncSession = Depends(get_db)):
    return PlansRepository(db=db)

async def get_tenant_repo(db: AsyncSession = Depends(get_db)):
    return TenantsRepository(db=db)

async def get_subscription_service(
    sub_repo: SubscriptionsRepository = Depends(get_subscription_repo),
    plans_repo: PlansRepository = Depends(get_plans_repo)
):
    return SubscriptionsService(subscription_repo=sub_repo, plans_repo=plans_repo)

async def get_plans_service(repo: PlansRepository = Depends(get_plans_repo)):
    return PlansService(repo=repo)

async def get_tenant_service(repo: TenantsRepository = Depends(get_tenant_repo)):
    return TenantsService(repo=repo)

@payment_router.get("/checkout/{subscription_id}")
async def paymob_checkout(
    subscription_id: uuid.UUID,
    sub_service: SubscriptionsService = Depends(get_subscription_service),
    plan_service: PlansService = Depends(get_plans_service),
    tenant_service: TenantsService = Depends(get_tenant_service)
):
    try:
        # 1. Fetch subscription details
        sub = await sub_service.get_subscription(subscription_id)
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")

        # 2. Fetch plan details
        plan = await plan_service.repo.get_plan_by_name(sub.plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        # 3. Fetch tenant details
        tenant = await tenant_service.get_tenant_by_id(sub.tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Calculate amount in cents
        price = plan.monthly_pricing if sub.subscription_type == "monthly" else plan.annual_pricing
        amount_cents = price * 100

        # Paymob Auth Request
        async with httpx.AsyncClient() as client:
            # Step 1: Authentication
            auth_response = await client.post(
                "https://accept.paymob.com/api/auth/tokens",
                json={"api_key": Config.PAYMOB_API_KEY},
                headers={"Content-Type": "application/json"}
            )
            if auth_response.status_code != 201 and auth_response.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to authenticate with Paymob")
            auth_token = auth_response.json().get("token")

            # Step 2: Order Registration
            import time
            unique_merchant_order_id = f"{subscription_id}_{int(time.time())}"
            order_payload = {
                "auth_token": auth_token,
                "delivery_needed": "false",
                "amount_cents": str(amount_cents),
                "currency": "EGP",
                "merchant_order_id": unique_merchant_order_id,
                "items": []
            }
            order_response = await client.post(
                "https://accept.paymob.com/api/ecommerce/orders",
                json=order_payload,
                headers={"Content-Type": "application/json"}
            )
            if order_response.status_code != 201 and order_response.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Failed to register order with Paymob: {order_response.text}")
            order_id = order_response.json().get("id")

            # Step 3: Payment Key Generation
            first_name = tenant.name.split()[0] if tenant.name else "Tenant"
            last_name = tenant.name.split()[-1] if len(tenant.name.split()) > 1 else "User"
            
            # Paymob accepts integers for integration_id
            try:
                integration_id = int(Config.PAYMOB_INTEGRATION_ID)
            except ValueError:
                integration_id = 0

            payment_key_payload = {
                "auth_token": auth_token,
                "amount_cents": str(amount_cents),
                "expiration": 3600,
                "order_id": str(order_id),
                "billing_data": {
                    "apartment": "NA",
                    "email": tenant.contact_email or "no-email@example.com",
                    "floor": "NA",
                    "first_name": first_name,
                    "street": "NA",
                    "building": "NA",
                    "phone_number": tenant.phone_no or "01000000000",
                    "shipping_method": "NA",
                    "postal_code": "NA",
                    "city": "NA",
                    "country": "NA",
                    "last_name": last_name,
                    "state": "NA"
                },
                "currency": "EGP",
                "integration_id": integration_id,
                "lock_order_to_card": False
            }
            key_response = await client.post(
                "https://accept.paymob.com/api/acceptance/payment_keys",
                json=payment_key_payload,
                headers={"Content-Type": "application/json"}
            )
            if key_response.status_code != 201 and key_response.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Failed to generate payment key: {key_response.text}")
            payment_token = key_response.json().get("token")

        # Redirect customer to credit card iframe
        iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{Config.PAYMOB_IFRAME_ID}?payment_token={payment_token}"
        return RedirectResponse(url=iframe_url, status_code=status.HTTP_303_SEE_OTHER)

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def verify_paymob_hmac(payload: dict, received_hmac: str, secret: str) -> bool:
    import hmac
    import hashlib

    obj = payload.get("obj", {})
    if not obj:
        return False
    
    def format_val(val):
        if isinstance(val, bool):
            return "true" if val else "false"
        if val is None:
            return ""
        return str(val)

    order_val = ""
    order_obj = obj.get("order", {})
    if isinstance(order_obj, dict):
        order_val = format_val(order_obj.get("id"))
    else:
        order_val = format_val(order_obj)

    source_data_obj = obj.get("source_data", {})
    source_data_pan = ""
    source_data_sub_type = ""
    source_data_type = ""
    if isinstance(source_data_obj, dict):
        source_data_pan = format_val(source_data_obj.get("pan"))
        source_data_sub_type = format_val(source_data_obj.get("sub_type"))
        source_data_type = format_val(source_data_obj.get("type"))

    concatenated = (
        format_val(obj.get("amount_cents")) +
        format_val(obj.get("created_at")) +
        format_val(obj.get("currency")) +
        format_val(obj.get("error_occured")) +
        format_val(obj.get("has_parent_transaction")) +
        format_val(obj.get("id")) +
        format_val(obj.get("integration_id")) +
        format_val(obj.get("is_3d_secure")) +
        format_val(obj.get("is_auth")) +
        format_val(obj.get("is_capture")) +
        format_val(obj.get("is_refunded")) +
        format_val(obj.get("is_standalone_payment")) +
        format_val(obj.get("is_voided")) +
        order_val +
        format_val(obj.get("owner")) +
        format_val(obj.get("pending")) +
        source_data_pan +
        source_data_sub_type +
        source_data_type +
        format_val(obj.get("success"))
    )

    computed_hmac = hmac.new(
        secret.encode("utf-8"),
        concatenated.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_hmac, received_hmac)


@payment_router.post("/paymob-callback")
async def paymob_callback(
    payload: dict,
    hmac: str,
    sub_service: SubscriptionsService = Depends(get_subscription_service)
):
    # Verify HMAC
    if not verify_paymob_hmac(payload, hmac, Config.PAYMOB_HMAC_SECRET):
        raise HTTPException(status_code=400, detail="Invalid HMAC signature")

    obj = payload.get("obj", {})
    success = obj.get("success")
    
    # If successful, activate the subscription in the database
    if success is True or str(success).lower() == "true":
        order_obj = obj.get("order", {})
        subscription_id_str = ""
        if isinstance(order_obj, dict):
            subscription_id_str = order_obj.get("merchant_order_id")
        else:
            subscription_id_str = order_obj
        
        if not subscription_id_str:
            raise HTTPException(status_code=400, detail="No merchant_order_id found in payment order payload")
            
        # Extract original subscription_id in case a suffix was added (e.g. uuid_timestamp)
        if "_" in subscription_id_str:
            subscription_id_str = subscription_id_str.split("_")[0]
            
        try:
            subscription_id = uuid.UUID(subscription_id_str)
            await sub_service.activate(subscription_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid subscription ID format in merchant_order_id")
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error))
            
    return {"status": "success"}
