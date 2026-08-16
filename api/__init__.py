"""HTTP layer.

Blueprints parse the request, call a service and serialise the result. No
business rules live here -- if a rule needs writing, it belongs in services/.
"""
from api.auth import require_staff  # noqa: F401
from api.routes import api_bp  # noqa: F401
