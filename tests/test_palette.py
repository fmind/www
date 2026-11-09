"""Keep authored interface colors within the independently buildable Fmind palette."""

import re
from pathlib import Path

from www.data import SERVICES

# Snapshot of the fmind/theme DESIGN.md colors; company identities are deliberate exceptions.
FMIND_COLORS = {
    "#ffffff",
    "#202124",
    "#595d62",
    "#174ea6",
    "#4285f4",
    "#a50e0e",
    "#ea4335",
    "#0d652d",
    "#34a853",
    "#934900",
    "#e37400",
    "#fbbc04",
    "#681da8",
    "#00636d",
    "#f1f3f4",
    "#9aa0a6",
    "#d2e3fc",
    "#fad2cf",
    "#feefc3",
    "#ceead6",
}


def test_service_badge_colors_are_exactly_the_safelisted_ones() -> None:
    # The home page builds `badge-<type> text-<type>-content` from data, which Tailwind cannot see in a template.
    stylesheet = Path("assets/css/input.css").read_text()
    safelist = re.search(r'@source inline\("badge-\{([a-z,]+)\} text-\{([a-z,]+)\}-content"\);', stylesheet)

    assert safelist, "the service badge safelist is missing from assets/css/input.css"
    assert safelist[1] == safelist[2]
    assert set(safelist[1].split(",")) == {service.badge_type for service in SERVICES}, (
        "add the new badge type to the @source inline safelist, or drop the unused one"
    )


def test_interface_palette_has_no_unreviewed_colors() -> None:
    stylesheet = Path("assets/css/input.css").read_text()
    interface = re.sub(r"\[data-company='[^']+'\]\s*\{[^}]*\}", "", stylesheet)
    colors = set(re.findall(r"#[0-9a-fA-F]{6}\b", interface.lower()))
    assert colors <= FMIND_COLORS, f"Non-theme interface colors: {sorted(colors - FMIND_COLORS)}"
