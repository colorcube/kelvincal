"""Prepared adapter for GNOME / Mutter (via colord and org.gnome.Mutter.DisplayConfig)."""

from __future__ import annotations

from .base import CompositorBackend, CompositorOutputState


class MutterBackend(CompositorBackend):
    """Stub implementation for future GNOME/Mutter support."""

    @property
    def name(self) -> str:
        return "mutter"

    def get_outputs(self) -> dict[str, CompositorOutputState]:
        return {}

    def apply_output_profile(
        self,
        connector: str,
        icc_profile_path: str = "",
        color_profile_source: str = "ICC",
        brightness: float | None = None,
        disable_hdr_wcg: bool = False,
    ) -> None:
        raise NotImplementedError(
            "GNOME/Mutter backend is prepared as an extension point and not yet enabled."
        )

    def apply_batch(self, updates: list[dict[str, object]]) -> None:
        for upd in updates:
            self.apply_output_profile(
                connector=str(upd["connector"]),
                icc_profile_path=str(upd.get("icc_profile_path", "")),
                color_profile_source=str(upd.get("color_profile_source", "ICC")),
                brightness=upd.get("brightness"),  # type: ignore[arg-type]
                disable_hdr_wcg=bool(upd.get("disable_hdr_wcg", False)),
            )
