import pytest

from manga_panels.split import split_wide


def test_narrow_panel_is_untouched():
    box = (10, 20, 80, 100)                            # ratio 0.8 <= 1.0
    assert split_wide(box, [], max_ratio=1.0) == [box]


def test_wide_panel_splits_into_ceil_ratio_slices():
    parts = split_wide((0, 0, 300, 100), [], max_ratio=1.0)
    assert len(parts) == 3                             # ratio 3.0 -> 3 slices


def test_slices_tile_the_panel_exactly():
    parts = split_wide((10, 20, 300, 100), [], max_ratio=1.0)
    assert sum(w for _, _, w, _ in parts) == 300
    assert all(y == 20 and h == 100 for _, y, _, h in parts)
    spans = sorted((x, x + w) for x, _, w, _ in parts)
    assert spans[0][0] == 10 and spans[-1][1] == 310   # covers the panel
    assert all(a[1] == b[0] for a, b in zip(spans, spans[1:]))   # no gap, no overlap


def test_slices_come_right_to_left():
    xs = [x for x, _, _, _ in split_wide((0, 0, 300, 100), [], max_ratio=1.0)]
    assert xs == sorted(xs, reverse=True)              # manga reading order


def test_seam_dodges_a_balloon():
    balloon = [90, 10, 112, 90]                        # straddles the ideal seam at x=100
    parts = split_wide((0, 0, 300, 100), [balloon], max_ratio=1.0)
    seams = sorted(x for x, _, _, _ in parts)[1:]
    assert all(not (balloon[0] < s < balloon[2]) for s in seams)


def test_obstacle_outside_the_panel_rows_is_ignored():
    far = [90, 200, 112, 300]                          # same columns, but below the panel
    parts = split_wide((0, 0, 300, 100), [far], max_ratio=1.0)
    assert sorted(x for x, _, _, _ in parts) == [0, 100, 200]    # seams stay ideal


def test_never_produces_a_zero_width_slice():
    # 3px wide, ratio 3.0, max_ratio 0.5 -> 6 slices of 0.5px would be degenerate
    parts = split_wide((0, 0, 3, 1), [], max_ratio=0.5)
    assert sum(w for _, _, w, _ in parts) == 3
    assert all(w >= 1 for _, _, w, _ in parts)


def test_max_ratio_must_be_positive():
    with pytest.raises(ValueError):
        split_wide((0, 0, 300, 100), [], max_ratio=0)
