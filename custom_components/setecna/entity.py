"""Base entity Setecna."""
from __future__ import annotations
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import SetecnaCoordinator
from .params import ParamDef


def system_device(system_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, system_id)},
        manufacturer="Setecna",
        model="REG system",
        name=f"Setecna {system_id}",
    )


class SetecnaEntity(CoordinatorEntity[SetecnaCoordinator]):
    """Base: lega un ParamDef al coordinator + device del sistema."""

    def __init__(self, coordinator: SetecnaCoordinator, system_id: str, param: ParamDef) -> None:
        super().__init__(coordinator)
        self._param = param
        self._sid = system_id
        self._attr_unique_id = f"{system_id}_{param.key}"
        self._attr_name = param.name
        self._attr_device_info = system_device(system_id)

    @property
    def _raw(self) -> str | None:
        return (self.coordinator.data or {}).get(self._param.key)

    @property
    def available(self) -> bool:
        return super().available and self._raw is not None


class SetecnaExtraEntity(CoordinatorEntity[SetecnaCoordinator]):
    """Base per entità non legate a un singolo parametro (orologi, editor, calendario)."""

    def __init__(self, coordinator: SetecnaCoordinator, system_id: str, suffix: str, name: str) -> None:
        super().__init__(coordinator)
        self._sid = system_id
        self._attr_unique_id = f"{system_id}_{suffix}"
        self._attr_name = name
        self._attr_device_info = system_device(system_id)

    @property
    def _d(self) -> dict:
        return self.coordinator.data or {}


class EditorEntity(SetecnaExtraEntity):
    """Entità dell'editor orologi: si aggiorna anche quando cambia la bozza."""

    def __init__(self, coordinator, system_id, suffix, name) -> None:
        super().__init__(coordinator, system_id, suffix, name)
        self._ed = coordinator.clock_editor

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._ed.add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return super().available and self._ed.clock is not None
