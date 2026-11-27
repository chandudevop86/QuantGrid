"""Read-only, fail-closed Dhan account identity validation.

Never trust an account ID from an HTTP request or caller-controlled broker
snapshot. Call with the server-created Dhan SDK and a trusted account ID
from the authenticated server-side broker configuration.
"""
class DhanIdentityUnavailable(RuntimeError):
    pass


def verify_dhan_account_identity(*, sdk_client, configured_client_id):
    if not isinstance(configured_client_id, str) or not configured_client_id.strip():
        raise DhanIdentityUnavailable("trusted broker client ID missing")
    if sdk_client is None:
        raise DhanIdentityUnavailable("authenticated Dhan client missing")
    try:
        response = sdk_client.get_fund_limits()
    except Exception as exc:
        raise DhanIdentityUnavailable("Dhan authenticated account probe failed") from exc
    if not isinstance(response, dict):
        raise DhanIdentityUnavailable("Dhan account probe schema invalid")
    if str(response.get("status", "")).lower() not in ("success", "successful"):
        raise DhanIdentityUnavailable("Dhan account probe unsuccessful")
    data = response.get("data")
    if not isinstance(data, dict):
        raise DhanIdentityUnavailable("Dhan account probe data missing")
    # Do not infer identity from a successful funds request alone. Dhan SDK
    # response schemas differ; absent explicit client identity must fail closed.
    broker_id = data.get("dhanClientId")
    if not isinstance(broker_id, str) or broker_id != configured_client_id:
        raise DhanIdentityUnavailable("Dhan account identity absent or mismatched")
    return broker_id
