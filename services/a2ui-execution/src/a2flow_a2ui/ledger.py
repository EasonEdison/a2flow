"""Atomic A2UI v0.9.1 message reducer and canonical snapshot encoder."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from a2flow_capability.models import JsonObject, JsonValue

from .jsonutil import require_object, require_size, write
from .models import A2uiError

PROTOCOL_VERSION = "v0.9.1"
OPERATIONS = {"createSurface", "updateComponents", "updateDataModel", "deleteSurface"}


@dataclass(slots=True)
class Surface:
    create: JsonObject
    components: dict[str, JsonObject] = field(default_factory=dict)
    data_model_defined: bool = False
    data_model: JsonValue = None


@dataclass(slots=True)
class SurfaceLedger:
    surfaces: dict[str, Surface] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> SurfaceLedger:
        return cls()

    def has_surface(self, surface_id: str) -> bool:
        return surface_id in self.surfaces

    def reduce(self, batch: tuple[JsonObject, ...] | list[JsonObject]) -> SurfaceLedger:
        if not batch or len(batch) > 256:
            raise A2uiError("A2UI_MESSAGE_BATCH_INVALID")
        staging = copy.deepcopy(self)
        for message in batch:
            staging._apply(message)
        if len(staging.surfaces) > 64:
            raise A2uiError("A2UI_SNAPSHOT_LIMIT")
        for surface in staging.surfaces.values():
            if len(surface.components) > 4096:
                raise A2uiError("A2UI_SNAPSHOT_LIMIT")
        require_size(list(staging.snapshot()), 1024 * 1024, "A2UI_SNAPSHOT_LIMIT")
        return staging

    def _apply(self, message: JsonObject) -> None:
        if message.get("version") != PROTOCOL_VERSION:
            raise A2uiError("A2UI_PROTOCOL_VERSION_UNSUPPORTED")
        keys = [key for key in message if key != "version"]
        if len(keys) != 1 or keys[0] not in OPERATIONS or set(message) != {"version", keys[0]}:
            raise A2uiError("A2UI_MESSAGE_INVALID")
        operation = keys[0]
        body = require_object(message[operation], "A2UI_MESSAGE_INVALID")
        surface_id = body.get("surfaceId")
        if type(surface_id) is not str or not surface_id.strip():
            raise A2uiError("A2UI_MESSAGE_INVALID")
        if operation == "createSurface":
            if surface_id in self.surfaces:
                raise A2uiError("A2UI_MESSAGE_INVALID")
            self.surfaces[surface_id] = Surface(copy.deepcopy(body))
            return
        surface = self.surfaces.get(surface_id)
        if surface is None:
            raise A2uiError("A2UI_MESSAGE_INVALID")
        if operation == "deleteSurface":
            del self.surfaces[surface_id]
            return
        if operation == "updateComponents":
            raw = body.get("components")
            if not isinstance(raw, list):
                raise A2uiError("A2UI_MESSAGE_INVALID")
            seen: set[str] = set()
            for value in raw:
                component = require_object(value, "A2UI_MESSAGE_INVALID")
                component_id = component.get("id")
                if (
                    type(component_id) is not str
                    or not component_id.strip()
                    or component_id in seen
                ):
                    raise A2uiError("A2UI_MESSAGE_INVALID")
                seen.add(component_id)
                surface.components[component_id] = copy.deepcopy(component)
            return
        path = body.get("path")
        if type(path) is not str or "value" not in body:
            raise A2uiError("A2UI_MESSAGE_INVALID")
        if path == "/":
            surface.data_model = copy.deepcopy(body["value"])
        else:
            root: JsonValue = surface.data_model if surface.data_model_defined else {}
            surface.data_model = write(root, path, body["value"])
        surface.data_model_defined = True

    def snapshot(self) -> tuple[JsonObject, ...]:
        messages: list[JsonObject] = []
        for surface in self.surfaces.values():
            messages.append(
                {"version": PROTOCOL_VERSION, "createSurface": copy.deepcopy(surface.create)}
            )
            if surface.components:
                messages.append(
                    {
                        "version": PROTOCOL_VERSION,
                        "updateComponents": {
                            "surfaceId": surface.create["surfaceId"],
                            "components": [
                                copy.deepcopy(item) for item in surface.components.values()
                            ],
                        },
                    }
                )
            if surface.data_model_defined:
                messages.append(
                    {
                        "version": PROTOCOL_VERSION,
                        "updateDataModel": {
                            "surfaceId": surface.create["surfaceId"],
                            "path": "/",
                            "value": copy.deepcopy(surface.data_model),
                        },
                    }
                )
        require_size(list(messages), 1024 * 1024, "A2UI_SNAPSHOT_LIMIT")
        return tuple(messages)

    @classmethod
    def replay(cls, messages: tuple[JsonObject, ...]) -> SurfaceLedger:
        if not messages:
            return cls.empty()
        return cls.empty().reduce(messages)
