"""Content tags → wp_color_manager_v1 image-description requests.

A declaration plan says which requests build the parametric creator for a
KelvinCal colour space, and which protocol capabilities it needs. The plan and
core.colorspaces must stay the same definition: whatever is declared here is
what verification patches are encoded in and graded against.

Protocol enum values are version 1 (the client binds v1; see cm-shim for the
v2/v3 naming changes). Sources: color-management-v1.xml.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kelvincal.core.colorspaces import (
    ADOBE_RGB,
    ColorSpace,
    DISPLAY_P3,
    REC2020_G22,
    SRGB,
)

# wp_color_manager_v1.primaries (named), version 1 values
PRIMARIES_SRGB = 1
PRIMARIES_BT2020 = 6
PRIMARIES_DISPLAY_P3 = 9
PRIMARIES_ADOBE_RGB = 10

# wp_color_manager_v1.transfer_function (named), version 1 values
TF_GAMMA22 = 2
TF_SRGB = 9

# wp_color_manager_v1.feature values
FEATURE_PARAMETRIC = 1
FEATURE_SET_TF_POWER = 3

# wp_color_manager_v1.render_intent
INTENT_PERCEPTUAL = 0
INTENT_RELATIVE = 1

# Verification needs the deterministic mapping (no perceptual gamut shaping,
# no black point compensation — profiles are built with BPC off).
DEFAULT_INTENT = INTENT_RELATIVE


@dataclass(frozen=True)
class DeclarationPlan:
    """The parametric-creator requests encoding `space`, and what they require."""

    space: ColorSpace
    primaries_named: int
    tf_named: int | None = None      # used when set; otherwise tf_power below
    tf_power: float | None = None    # pure-power TRC (Adobe RGB 1998: 563/256)
    required_features: frozenset[int] = field(default_factory=frozenset)

    def requests(self) -> list[tuple[str, object]]:
        """(request, value) pairs for wp_image_description_creator_params_v1."""
        out: list[tuple[str, object]] = [("set_primaries_named", self.primaries_named)]
        if self.tf_named is not None:
            out.append(("set_tf_named", self.tf_named))
        else:
            out.append(("set_tf_power", self.tf_power))
        return out


# The protocol's named TF `srgb` is the IEC 61966-2-1 piecewise curve — the
# same TRC core.colorspaces encodes for "srgb" spaces.
_PLANS: dict[str, DeclarationPlan] = {
    SRGB.name: DeclarationPlan(SRGB, PRIMARIES_SRGB, tf_named=TF_SRGB,
                                required_features=frozenset({FEATURE_PARAMETRIC})),
    DISPLAY_P3.name: DeclarationPlan(DISPLAY_P3, PRIMARIES_DISPLAY_P3, tf_named=TF_SRGB,
                                      required_features=frozenset({FEATURE_PARAMETRIC})),
    REC2020_G22.name: DeclarationPlan(REC2020_G22, PRIMARIES_BT2020, tf_named=TF_GAMMA22,
                                      required_features=frozenset({FEATURE_PARAMETRIC})),
    # Adobe RGB 1998 has a pure power TRC of 563/256: no named TF matches it,
    # so the declaration needs set_tf_power. Never approximate it as gamma22 —
    # the expectation would silently disagree with what was declared.
    ADOBE_RGB.name: DeclarationPlan(ADOBE_RGB, PRIMARIES_ADOBE_RGB, tf_power=563 / 256,
                                    required_features=frozenset({FEATURE_PARAMETRIC, FEATURE_SET_TF_POWER})),
}


def plan_for(space: ColorSpace) -> DeclarationPlan:
    try:
        return _PLANS[space.name]
    except KeyError:
        raise ValueError(f"no wp_color_manager declaration for colour space {space.name!r}") from None


def missing_features(plan: DeclarationPlan, supported_features: set[int]) -> set[int]:
    """Protocol features the compositor must list for this plan to be declarable."""
    return set(plan.required_features) - supported_features


def missing_primaries_tf(plan: DeclarationPlan, supported_primaries: set[int],
                         supported_tfs: set[int]) -> list[str]:
    """Capability checks the manager's named lists answer before creating a creator."""
    missing = []
    if plan.primaries_named not in supported_primaries:
        missing.append(f"primaries {plan.primaries_named}")
    if plan.tf_named is not None and plan.tf_named not in supported_tfs:
        missing.append(f"transfer function {plan.tf_named}")
    return missing
