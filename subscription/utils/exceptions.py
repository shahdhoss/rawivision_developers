class PlanNotFound(Exception):
    # raised when plan is not found in the database
    pass

class SubscriptionNotFound(Exception):
    pass

class TenantNotFound(Exception):
    pass

class InvalidStateTransition(Exception):
    pass
