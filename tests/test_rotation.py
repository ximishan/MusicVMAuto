from datetime import date

from music_auto.rotation import playlist_for_day


def test_two_playlist_rotation():
    base = date(2026, 8, 12)
    assert playlist_for_day(base, date(2026, 8, 12)) == 1
    assert playlist_for_day(base, date(2026, 8, 13)) == 2
    assert playlist_for_day(base, date(2026, 8, 14)) == 1
    assert playlist_for_day(base, date(2026, 8, 15)) == 2
