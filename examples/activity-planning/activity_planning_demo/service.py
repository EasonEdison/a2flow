"""Business side of the activity demo: a uniform RPC service implementation.

Implements the platform BusinessService protocol; the composition root
registers one instance per service name. The platform core never imports
this module. Everything here is demo business code, not platform code.
"""

from __future__ import annotations

from skillweave_contracts import TrustedContext

SERVICE_ACTIVITY_PLANNING = "activity-planning"
SERVICE_ACTIVITY_PACKAGE = "activity-package"


def _owner(owner):
    if type(owner) is not TrustedContext:
        raise ValueError("TRUSTED_CONTEXT_REQUIRED")


def budget_activity(arguments, owner):
    """Split a supplied minor-unit demo budget; does not obtain vendor quotes."""
    _owner(owner)
    if type(arguments) is not dict or set(arguments) != {"participants", "budgetMinor"}:
        raise ValueError("INVALID_BUDGET_ARGUMENTS")
    people, budget = arguments["participants"], arguments["budgetMinor"]
    if type(people) is not int or not 1 <= people <= 100000:
        raise ValueError("INVALID_PARTICIPANTS")
    if type(budget) is not int or not 0 <= budget <= 10**12:
        raise ValueError("INVALID_BUDGET")
    quotient, remainder = divmod(budget, people)
    return {"participants": people, "budgetMinor": budget,
            "perPersonMinor": quotient, "remainderMinor": remainder}


def select_activity(arguments, owner):
    """Return a local confirmation after Runtime validates its saved option set.

    This pure function cannot establish interaction authority. It must be bound
    only to the configured Action executor and never model execute_ability.
    """
    _owner(owner)
    if type(arguments) is not dict or set(arguments) != {"optionId", "confirmed"}:
        raise ValueError("INVALID_SELECTION_ARGUMENTS")
    if type(arguments["optionId"]) is not str or not 1 <= len(arguments["optionId"]) <= 128:
        raise ValueError("INVALID_OPTION")
    if arguments["confirmed"] is not True:
        raise ValueError("CONFIRMATION_REQUIRED")
    return {"selectedOptionId": arguments["optionId"], "confirmed": True}


def choose_package_plan(arguments, owner):
    """Save one card-bound choice; Runtime establishes interaction authority."""
    _owner(owner)
    if (type(arguments) is not dict or set(arguments) != {"optionId"}
            or type(arguments["optionId"]) is not str
            or not 1 <= len(arguments["optionId"]) <= 128):
        raise ValueError("INVALID_SELECTION_ARGUMENTS")
    return {"selectedOptionId": arguments["optionId"]}


def confirm_package_schedule(arguments, owner):
    """Save one card-bound schedule confirmation without external side effects."""
    _owner(owner)
    if (type(arguments) is not dict or set(arguments) != {"optionId", "confirmed"}
            or type(arguments["optionId"]) is not str
            or not 1 <= len(arguments["optionId"]) <= 128
            or arguments["confirmed"] is not True):
        raise ValueError("INVALID_CONFIRMATION_ARGUMENTS")
    return {"selectedOptionId": arguments["optionId"], "confirmed": True}


_METHODS = {
    (SERVICE_ACTIVITY_PLANNING, "budget"): budget_activity,
    (SERVICE_ACTIVITY_PLANNING, "select"): select_activity,
    (SERVICE_ACTIVITY_PACKAGE, "select"): choose_package_plan,
    (SERVICE_ACTIVITY_PACKAGE, "confirm-schedule"): confirm_package_schedule,
}


class ActivityPlanningService:
    """Typed RPC handler for both demo service names."""

    def invoke(self, *, service, method, arguments, owner):
        handler = _METHODS.get((service, method))
        if handler is None:
            raise LookupError("BUSINESS_METHOD_NOT_FOUND")
        return handler(arguments, owner)
