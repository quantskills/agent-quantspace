from __future__ import annotations

import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from matplotlib.ft2font import FT2Font

from skills.report.charts import fig_to_png, plot_equity_curve
from skills.report.fonts import (
    apply_cjk_font,
    configure_cjk_matplotlib,
    find_cjk_font_path,
    reset_cjk_font_cache,
)


def test_windows_font_candidates_use_windir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from skills.report import fonts

    fonts_dir = tmp_path / "Windows" / "Fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "MSYH.TTC").write_bytes(b"placeholder")
    (fonts_dir / "simhei.ttf").write_bytes(b"placeholder")
    monkeypatch.setattr(fonts.sys, "platform", "win32")
    monkeypatch.setitem(os.environ, "WINDIR", str(tmp_path / "Windows"))
    reset_cjk_font_cache()
    paths = fonts._windows_font_files()
    names = {path.name.lower() for path in paths}
    assert "msyh.ttc" in names
    assert "simhei.ttf" in names
    assert paths[0].name.lower() == "msyh.ttc"


def test_windows_prefers_msyh_over_other_system_fonts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from skills.report import fonts

    src = find_cjk_font_path()
    if src is None:
        pytest.skip("No CJK-capable font is installed on this machine")

    fonts_dir = tmp_path / "Windows" / "Fonts"
    fonts_dir.mkdir(parents=True)
    target = fonts_dir / "msyh.ttc"
    target.symlink_to(src)
    monkeypatch.setattr(fonts.sys, "platform", "win32")
    monkeypatch.setitem(os.environ, "WINDIR", str(tmp_path / "Windows"))
    reset_cjk_font_cache()

    found = find_cjk_font_path()
    assert found is not None
    assert Path(found).name.lower() == "msyh.ttc"
    family = configure_cjk_matplotlib()
    import matplotlib as mpl

    sans = [str(name) for name in mpl.rcParams["font.sans-serif"]]
    assert "Microsoft YaHei" in sans
    assert "微软雅黑" in sans
    assert family


def test_posix_catalog_style_paths_join_on_any_os(tmp_path: Path) -> None:
    study = tmp_path / "lesson_09" / "if_ma10_atr"
    study.mkdir(parents=True)
    target = study / "index.html"
    target.write_text("<html></html>\n", encoding="utf-8", newline="\n")
    relative = Path("lesson_09") / "if_ma10_atr" / "index.html"
    assert (tmp_path / relative) == target
    assert relative.as_posix() == "lesson_09/if_ma10_atr/index.html"


def test_configure_cjk_matplotlib_sets_unicode_minus() -> None:
    import matplotlib as mpl

    configure_cjk_matplotlib()
    assert mpl.rcParams["axes.unicode_minus"] is False


def test_chinese_title_uses_cjk_capable_font() -> None:
    reset_cjk_font_cache()
    font_path = find_cjk_font_path()
    if font_path is None:
        pytest.skip("No CJK-capable font is installed on this machine")

    configure_cjk_matplotlib()
    fig, ax = plt.subplots()
    ax.set_title("策略净值与回撤")
    apply_cjk_font(fig)
    fname = ax.title.get_fontproperties().get_file()
    plt.close(fig)
    assert fname
    assert FT2Font(fname).get_char_index(ord("中")) != 0

    png = plot_equity_curve(
        pd.Series([0.01, -0.01], index=pd.date_range("2024-01-01", periods=2)),
        title="累计收益",
    )
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 100


def test_fig_to_png_closes_figure() -> None:
    fig, ax = plt.subplots()
    ax.set_title("demo")
    number = fig.number
    png = fig_to_png(fig)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert number not in plt.get_fignums()
