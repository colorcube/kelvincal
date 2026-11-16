"""Tagged verification: patches with an explicit wp_color_manager tag through the compositor.

The complementary mode to raw verification: patches are tagged `content_space`
so the compositor transforms them through the active ICC, and the measurements
are graded against the tag's own definition. A pass means the delivery chain
(tag -> compositor ICC -> device) is correct for that space. On KWin 6.8 only
gamma22 transfer functions are declarable (no named sRGB TF, no set_tf_power),
which makes rec2020 the widest tag this compositor accepts.
"""

from __future__ import annotations

from dataclasses import dataclass

from kelvincal.argyll.spotread_session import SpotreadSession
from kelvincal.core.color import xyz_to_lab
from kelvincal.core.colorspaces import ColorSpace, rgb8_to_xyz, space_by_name
from kelvincal.core.verification import VerificationResult, evaluate, test_patches
from kelvincal.wayland_cm.cm import ColorManagerConnection
from kelvincal.wayland_cm.display import TaggedPatchWindow
from kelvincal.wayland_cm.tags import plan_for

D65 = (0.31271, 0.32902)
WHITE_SETTLE_S = 1.0


@dataclass
class TaggedReport:
    verification: VerificationResult
    compositor_primaries: str      # what the output description claimed


def tagged_verify(
    connector: str,
    content_tag: str,
    ccss_path: str | None = None,
    display_type: str = "l",
    settle_s: float = 0.5,
    sensor_settle_s: float = 0.15,
) -> TaggedReport:
    """Measures tagged patches through the compositor and grades them against the tag.

    Shows a fullscreen window on the panel — never run while a measurement is
    in flight. The profile under test must be active in the compositor.
    """
    space: ColorSpace = space_by_name(content_tag)
    plan = plan_for(space)
    patches = test_patches(space)
    target = space.white_xy

    conn = ColorManagerConnection()
    try:
        output_info = conn.output_description(connector)
        window = TaggedPatchWindow(conn, connector, plan, settle_s=settle_s)
        window.open()
        try:
            with SpotreadSession(display_type=display_type, ccss_path=ccss_path,
                                 settle_before_measure_s=sensor_settle_s) as sensor:
                window.show((255, 255, 255))
                white = sensor.measure_rgb((255, 255, 255), timeout_s=30.0)
                window.show((0, 0, 0))
                black = sensor.measure_rgb((0, 0, 0), timeout_s=60.0)
                measured = []
                for patch in patches:
                    window.show(patch.rgb)
                    m = sensor.measure_rgb(patch.rgb, timeout_s=30.0)
                    measured.append((m.X, m.Y, m.Z))
        finally:
            window.close()
    finally:
        conn.close()

    white_xyz = (white.X, white.Y, white.Z)
    result = evaluate(patches, measured, white_xyz, (black.X, black.Y, black.Z),
                      target, plan.space.label, connector)
    return TaggedReport(verification=result, compositor_primaries=output_info.primaries_str())
