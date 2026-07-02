import colorsys
import unittest

from PySide6.QtGui import QColor

from tide.ui.adaptive import pick_accent, pick_accent_alt, pick_bg_tint


def _hue(c: QColor) -> float:
    return colorsys.rgb_to_hls(c.redF(), c.greenF(), c.blueF())[0] * 360.0


def _hue_distance(a: QColor, b: QColor) -> float:
    d = abs(_hue(a) - _hue(b))
    return min(d, 360.0 - d)


class AdaptivePaletteTests(unittest.TestCase):
    def test_muted_green_mass_beats_tiny_warm_outliers(self) -> None:
        palette = [
            (QColor("#667568"), 2600),
            (QColor("#727871"), 900),
            (QColor("#d9bf35"), 80),
            (QColor("#e35b9a"), 60),
        ]
        accent = pick_accent(palette, QColor("#0b0b0b"))
        tint = pick_bg_tint(palette)
        self.assertIsNotNone(accent)
        self.assertIsNotNone(tint)
        self.assertGreaterEqual(_hue(accent), 85.0)
        self.assertLessEqual(_hue(accent), 165.0)
        self.assertGreaterEqual(_hue(tint), 85.0)
        self.assertLessEqual(_hue(tint), 165.0)
        self.assertLess(_hue_distance(pick_accent_alt(palette, accent, QColor("#0b0b0b")), accent), 8.0)

    def test_secondary_hue_needs_real_palette_mass(self) -> None:
        palette = [
            (QColor("#6f1919"), 1700),
            (QColor("#451313"), 850),
            (QColor("#2d58d9"), 90),
        ]
        accent = pick_accent(palette, QColor("#0b0b0b"))
        alt = pick_accent_alt(palette, accent, QColor("#0b0b0b"))
        self.assertIsNotNone(accent)
        self.assertLess(_hue_distance(alt, accent), 8.0)

    def test_real_second_hue_can_be_used(self) -> None:
        palette = [
            (QColor("#366b45"), 1800),
            (QColor("#713b85"), 1400),
            (QColor("#202020"), 600),
        ]
        accent = pick_accent(palette, QColor("#0b0b0b"))
        alt = pick_accent_alt(palette, accent, QColor("#0b0b0b"))
        self.assertIsNotNone(accent)
        self.assertGreater(_hue_distance(alt, accent), 60.0)

    def test_grayscale_palette_has_no_fake_album_hue(self) -> None:
        palette = [
            (QColor("#777777"), 1800),
            (QColor("#4c4c4c"), 1200),
            (QColor("#a0a0a0"), 400),
            (QColor("#de4a5f"), 35),
        ]
        self.assertIsNone(pick_accent(palette, QColor("#0b0b0b")))
        self.assertIsNone(pick_bg_tint(palette))


if __name__ == "__main__":
    unittest.main()
