from __future__ import annotations

"""Shared marker base class for Hydros hub implementations.

Both the legacy account-credential hub (:class:`~custom_components.hydros.hydros_hub.HydrosHub`)
and the official Public API hub
(:class:`~custom_components.hydros.api_hub.HydrosApiHub`) subclass this so the
rest of the integration can accept either with a single ``isinstance`` check.

The entity platforms read collective state through a common surface:

* ``collective_ids`` / ``entry_id``
* ``get_collective_metadata`` / ``async_get_collective_config``
* ``get_input_value`` / ``get_input_metadata`` / ``get_input_payload``
* ``get_output_value`` / ``get_output_metadata`` / ``get_output_payload``
* ``get_output_capabilities``
* ``get_collective_status_payload`` / ``get_latest_status_ts``
* ``get_api_health`` / ``get_command_status`` / ``get_pending_command_count``
* ``signal_for_collective`` / ``signal_for_config``
* ``async_subscribe_collective_status``
* ``async_change_mode`` / ``async_set_output_state`` / ``async_set_pump_speed`` /
  ``async_manual_dose``

Concrete hubs are free to implement unsupported bits as no-ops (for example the
API hub has no MQTT subscription and no dosing-log history).
"""


class HydrosHubBase:
    """Marker base class shared by all Hydros hub implementations."""

    # Whether the hub can populate the per-doser "Dosed Today" history sensor.
    # The official Public API exposes no dosing-log endpoint, so the API hub
    # sets this to ``False`` and those sensors are not created.
    supports_dosing_history: bool = True
