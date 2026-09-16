"""Keep authored interface colors within the independently buildable Fmind palette."""

import re
from pathlib import Path

# Snapshot of fmind/theme checks/palette.yaml; company identities are deliberate exceptions.
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


def test_interface_palette_has_no_unreviewed_colors() -> None:
    stylesheet = Path("assets/css/input.css").read_text()
    interface = re.sub(r"\[data-company='[^']+'\]\s*\{[^}]*\}", "", stylesheet)
    colors = set(re.findall(r"#[0-9a-fA-F]{6}\b", interface.lower()))
    assert colors <= FMIND_COLORS, f"Non-theme interface colors: {sorted(colors - FMIND_COLORS)}"
