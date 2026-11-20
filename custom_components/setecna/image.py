"""Grafico della curva climatica di ogni circuito (immagine SVG generata dai parametri)."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .circuits import circuits_present, curve_info, render_svg
from .const import CONF_SYSTEM_ID, DOMAIN
from .entity import SetecnaExtraEntity
from .params import descr_label


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    sid = entry.data[CONF_SYSTEM_ID]
    raw = coord.data or {}
    add(CircuitCurveImage(hass, coord, sid, i, descr_label(raw, f"C{i}_DESCR") or str(i))
        for i in circuits_present(raw))


class CircuitCurveImage(SetecnaExtraEntity, ImageEntity):
    """Curva della stagione attiva (comfort + economy) con il punto di lavoro attuale."""

    _attr_content_type = "image/svg+xml"
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    def __init__(self, hass, coordinator, system_id, circuit: int, name: str) -> None:
        SetecnaExtraEntity.__init__(self, coordinator, system_id, f"circuit_{circuit}_curve",
                                    f"Circuito {name} curva climatica")
        ImageEntity.__init__(self, hass)
        self._circuit = circuit
        self._cname = name
        self._svg = render_svg(self._d, circuit, name)
        self._attr_image_last_updated = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        svg = render_svg(self._d, self._circuit, self._cname)
        if svg != self._svg:  # nuova versione solo se il grafico cambia davvero
            self._svg = svg
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        return self._svg

    @property
    def extra_state_attributes(self):
        return {"circuito": self._circuit, **curve_info(self._d, self._circuit)}
