from webview_overlay.layout import (
    anchor_in_bounds,
    anchor_on_any_monitor,
    monitor_containing,
)

PRIMARY = (0, 0, 1920, 1080)
SECONDARY = (1920, 0, 1920, 1080)
MONITORS = [PRIMARY, SECONDARY]


def test_anchor_within_bounds():
    # bottom-right anchor 20px from the edges, 180x420 window → fits
    assert anchor_in_bounds(1900, 1060, 180, 420, PRIMARY) is True


def test_anchor_off_screen_left():
    # anchor_r smaller than width pushes x negative
    assert anchor_in_bounds(100, 1060, 180, 420, PRIMARY) is False


def test_anchor_off_screen_bottom():
    # anchor_b beyond monitor height
    assert anchor_in_bounds(1900, 2000, 180, 420, PRIMARY) is False


def test_anchor_secondary_monitor_offset():
    secondary = (1920, 0, 1920, 1080)
    assert anchor_in_bounds(3820, 1060, 180, 420, secondary) is True
    assert anchor_in_bounds(1900, 1060, 180, 420, secondary) is False


def test_anchor_on_any_monitor_accepts_secondary():
    # Anchor on the secondary monitor: invalid vs primary alone, valid vs the set.
    assert anchor_in_bounds(3820, 1060, 180, 420, PRIMARY) is False
    assert anchor_on_any_monitor(3820, 1060, 180, 420, MONITORS) is True


def test_anchor_on_any_monitor_rejects_off_screen():
    # Beyond every monitor's right edge → no monitor can hold it.
    assert anchor_on_any_monitor(9000, 1060, 180, 420, MONITORS) is False


def test_monitor_containing_picks_secondary():
    # A point on the secondary monitor returns the secondary rect, not primary.
    assert monitor_containing(MONITORS, PRIMARY, 2500, 500) == SECONDARY
    assert monitor_containing(MONITORS, PRIMARY, 100, 500) == PRIMARY


def test_monitor_containing_falls_back_to_primary():
    # Point off every monitor → primary fallback (so clamp stays sane).
    assert monitor_containing(MONITORS, PRIMARY, -500, -500) == PRIMARY
    assert monitor_containing([], PRIMARY, 100, 100) == PRIMARY
