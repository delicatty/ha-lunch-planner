"""Texts that are not part of a form: notifications, calendar titles, names.

Home Assistant has no translation category for notification bodies, so they
are kept in the translation files as the options of a ``notification``
selector, next to the panel's texts (``panel`` selector). That keeps every
user-facing string in ``translations/*.json``.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN

_PREFIX = f"component.{DOMAIN}.selector.notification.options."


async def async_load_texts(hass: HomeAssistant) -> dict[str, str]:
    """Notification texts in the Home Assistant language (English where missing)."""
    strings = await async_get_translations(
        hass, hass.config.language, "selector", {DOMAIN}
    )
    return {
        key.removeprefix(_PREFIX): value
        for key, value in strings.items()
        if key.startswith(_PREFIX)
    }
