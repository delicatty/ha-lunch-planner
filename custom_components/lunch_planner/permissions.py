"""Only admins change the meal database or draw lunches again.

Home Assistant has no per-action or per-entity permissions: any user may call
any action and press any button. So the actions and the button check the
user themselves. A call without a user (an automation or a script started by
one) is allowed, like Home Assistant's own admin-only actions.
"""

from __future__ import annotations

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import Unauthorized, UnknownUser


async def async_check_admin(hass: HomeAssistant, context: Context | None) -> None:
    """Raise Unauthorized when a user who is not an admin made the call."""
    if context is None or context.user_id is None:
        return
    user = await hass.auth.async_get_user(context.user_id)
    if user is None:
        raise UnknownUser(context=context)
    if not user.is_admin:
        raise Unauthorized(context=context)
