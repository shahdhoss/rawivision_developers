from ..repository.subscriptions import SubscriptionsRepository
from ..repository.plans import PlansRepository
from ..schemas.subscriptions import SubscriptionCreate, CheckInRequest
from ..schemas.license import LicenseTokenPayload
from ..services.license import LicenseService
from ..utils.exceptions import SubscriptionNotFound, InvalidStateTransition, PlanNotFound
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
import uuid

class SubscriptionsService:
    def __init__(self, subscription_repo: SubscriptionsRepository, plans_repo: PlansRepository):
        self.subscription_repo = subscription_repo
        self.plans_repo = plans_repo
        self.license_service = LicenseService()
        self.VALID_TRANSITIONS = {
            "trial":    {"active", "canceled", "expired"},
            "active":   {"past_due", "canceled", "expired"},
            "past_due": {"active", "canceled", "expired"},
            "canceled": set(),
            "expired":  set(),
        }
        self.TERMINAL_STATES = {"canceled", "expired"}
    
    # helper functions
    def _calculate_trial_end(self):
        now = datetime.now(timezone.utc)
        return now + timedelta(days=14)
        

    def _get_entitlements(self, plan_name: str):
        defaults = {"plan": plan_name}
        return defaults

    def _mint(self, sub):
        payload = LicenseTokenPayload(installation_uuid=sub.installation_uuid, tenant_id=sub.tenant_id, plan_id=sub.plan_id, subscription_state=sub.state, subscription_type=sub.subscription_type, entitlements=self._get_entitlements(sub.plan_id))
        return self.license_service.mint_token(payload)

    async def _get_or_raise(self, subscription_id: uuid.UUID):
        sub = await self.subscription_repo.get_by_id(subscription_id)
        if not sub:
            raise SubscriptionNotFound(f"Subscription {subscription_id} not found")
        return sub

    def _assert_transition(self, current_state: str, target_state: str):
        if target_state not in self.VALID_TRANSITIONS.get(current_state, set()):
            raise InvalidStateTransition(f"Cannot transition from '{current_state}' to '{target_state}'")
    
    def _check_active_subscription_tier(self, tier):
        if tier == "0":
            return {"status": "active", "message": "Subscription active", "attendance": True, "search": False, "summarization": False}
        elif tier == "1":
            return {"status": "active", "message": "Subscription active","attendance": True, "search": True, "summarization": False}
        elif tier == "2" :
            return {"status": "active", "message": "Subscription active","attendance": True, "search": True, "summarization": True}
        raise ValueError(f"Unknown tier: {tier}")

    async def create_subscription(self, subscription: SubscriptionCreate):
        try:
            plan = await self.plans_repo.get_plan_by_name(subscription.plan_id)
            if not plan:
                raise PlanNotFound(f"Plan '{subscription.plan_id}' not found")
            trial_ends_at = self._calculate_trial_end()
            sub = await self.subscription_repo.create_subscription(subscription=subscription, trial_ends_at=trial_ends_at)
            return sub
        except Exception as error:
            raise error
    
    async def get_all_subscriptions(self):
        try:
            subscriptions = await self.subscription_repo.get_all_subscriptions()
            return subscriptions
        except Exception as error:
            raise error

    
    # life cycle transitions
    async def activate(self, subscription_id: uuid.UUID):
        try:
            sub = await self._get_or_raise(subscription_id)
            self._assert_transition(sub.state, "active")
            now = datetime.now(timezone.utc)
            if sub.subscription_type == "monthly":
                cycle_end = now + relativedelta(months=1)
            else:
                cycle_end = now + relativedelta(years=1)
            sub = await self.subscription_repo.update_state(sub, "active", billing_cycle_start=now, billing_cycle_end=cycle_end)
            return sub
        except Exception as error:
            raise error

    async def mark_past_due(self, subscription_id: uuid.UUID):
        try:
            sub = await self._get_or_raise(subscription_id)
            self._assert_transition(sub.state, "past_due")
            sub = await self.subscription_repo.update_state(sub, "past_due")
            return sub
        except Exception as error:
            raise error

    async def cancel(self, subscription_id: uuid.UUID):
        try:
            sub = await self._get_or_raise(subscription_id)
            self._assert_transition(sub.state, "canceled")
            sub = await self.subscription_repo.update_state(sub, "canceled", canceled_at=datetime.now(timezone.utc))
            await self._fire_webhook(sub, "canceled")
            return sub
        except Exception as error:
            raise error

    async def expire(self, subscription_id: uuid.UUID):
        try:
            sub = await self._get_or_raise(subscription_id)
            self._assert_transition(sub.state, "expired")
            sub = await self.subscription_repo.update_state(sub, "expired")
            await self._fire_webhook(sub, "expired")
            return sub
        except Exception as error:
            raise error

    async def change_plan(self, subscription_id: uuid.UUID, new_plan_id: str):
        try:
            sub = await self._get_or_raise(subscription_id)
            if sub.state in self.TERMINAL_STATES:
                raise InvalidStateTransition("Cannot change plan on a terminal subscription")
            plan = await self.plans_repo.get_plan_by_name(new_plan_id)
            if not plan:
                raise PlanNotFound(f"Plan '{new_plan_id}' not found")
            sub = await self.subscription_repo.update_state(sub, sub.state, plan_id=new_plan_id)
            return sub
        except Exception as error:
            raise error


    async def check_in(self, subscription_id):
        try:
            sub = await self.subscription_repo.get_by_subscription_uuid(subscription_uuid=subscription_id)
            if not sub:
                return {"status": "suspended", "message": "No subscription found for this installation"}
            if sub.state in ("canceled", "expired"):
                return {"status": sub.state, "message": f"Subscription {sub.state}"}
            if sub.state == "past_due":
                return {"status": "suspended", "message": "Payment overdue"}
            plan_name = sub.plan_id
            plan = await self.plans_repo.get_plan_by_name(plan_name)
            if not plan:
                raise PlanNotFound(f"Plan '{plan_name}' not found")
            tier = plan.tier
            return self._check_active_subscription_tier(tier=tier)            
        except Exception as error:
            raise error

    async def get_subscription(self, subscription_id: uuid.UUID):
        try:
            return await self._get_or_raise(subscription_id)
        except Exception as error:
            raise error

    async def _fire_webhook(self, sub, status: str):
        try:
            plan = await self.plans_repo.get_plan_by_name(sub.plan_id)
            tier = plan.tier if plan else ""

            from ..models.usage_log import UsageLog
            from sqlalchemy import select
            log_res = await self.subscription_repo.db.execute(
                select(UsageLog.installation_uuid)
                .where(UsageLog.subscription_id == sub.id)
                .order_by(UsageLog.received_at.desc())
                .limit(1)
            )
            installation_uuid = log_res.scalar_one_or_none()

            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    "http://localhost:8000/subscription/webhook/update",
                    json={
                        "installation_uuid": str(installation_uuid) if installation_uuid else "",
                        "status": status,
                        "tier": tier
                    },
                    timeout=5.0
                )
        except Exception as e:
            print(f"Failed to fire outbound webhook: {e}")

