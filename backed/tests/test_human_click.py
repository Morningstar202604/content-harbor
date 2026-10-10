# -*- coding: utf-8 -*-
"""拟人化操作回归（core/human_click.py）——此前零覆盖。

本模块的浏览器交互路径需要真实页面，只测纯计算部分：
贝塞尔采样、落点夹取、候选选择器拼装。曲线算法的边界（steps<=0 的除零、
端点是否精确）是纯数学，可以完全确定性地断言。
"""

import pytest

from core.human_click import (OPTION_SELECTORS, curve_points, _visible_options)


class FakeLoc:
    def __init__(self, box, raise_on_box=False):
        self._box = box
        self._raise = raise_on_box
        self.moved = False

    def scroll_into_view_if_needed(self, timeout=None):
        self.moved = True

    def evaluate(self, script):
        self.moved = True

    def bounding_box(self):
        if self._raise:
            raise RuntimeError("no box")
        return self._box


class FakeMouse:
    def __init__(self, fail_down=False):
        self.events = []
        self._fail_down = fail_down

    def move(self, x, y):
        self.events.append(("move", x, y))

    def down(self):
        if self._fail_down:
            raise RuntimeError("driver gone")
        self.events.append(("down",))

    def up(self):
        self.events.append(("up",))


class FakePage:
    def __init__(self, mouse):
        self.mouse = mouse


# ---------------- 贝塞尔曲线 ----------------

def test_curve_endpoints_are_exact():
    pts = curve_points((0, 0), (50, 100), (100, 0), 10)
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (100.0, 0.0)


def test_curve_returns_steps_plus_one_points():
    assert len(curve_points((0, 0), (1, 1), (2, 0), 5)) == 6


@pytest.mark.parametrize("bad", [0, -1, -100])
def test_curve_survives_nonpositive_steps(bad):
    """steps<=0 会让 t = i/steps 除零——必须夹到 1 而不是崩在调用方。"""
    pts = curve_points((0, 0), (5, 5), (10, 0), bad)
    assert len(pts) == 2
    assert pts[0] == (0.0, 0.0) and pts[-1] == (10.0, 0.0)


def test_curve_coerces_fractional_steps():
    assert len(curve_points((0, 0), (1, 1), (2, 0), 3.9)) == 4


def test_curve_midpoint_follows_control():
    """二次贝塞尔 t=0.5 时落在起终中点与控制点的加权处。"""
    pts = curve_points((0, 0), (50, 100), (100, 0), 2)
    assert pts[1][0] == pytest.approx(50.0)
    assert pts[1][1] == pytest.approx(50.0)


def test_curve_control_beyond_endpoints_is_fine():
    """控制点可以任意夸张（模拟抖动），曲线不应因此发散。"""
    pts = curve_points((0, 0), (5000, -3000), (100, 0), 8)
    assert len(pts) == 9
    assert pts[0] == (0.0, 0.0) and pts[-1] == (100.0, 0.0)


# ---------------- move_and_click ----------------

def test_move_and_click_succeeds(monkeypatch):
    monkeypatch.setattr("core.human_click.time.sleep", lambda *_: None)
    from core.human_click import move_and_click
    mouse = FakeMouse()
    loc = FakeLoc({"x": 100, "y": 100, "width": 50, "height": 20})
    assert move_and_click(FakePage(mouse), loc) is True
    assert mouse.events[0][0] == "move"
    assert ("down",) in mouse.events and ("up",) in mouse.events
    assert loc.moved is True


def test_move_and_click_returns_false_when_box_missing(monkeypatch):
    monkeypatch.setattr("core.human_click.time.sleep", lambda *_: None)
    from core.human_click import move_and_click
    loc = FakeLoc(None)
    assert move_and_click(FakePage(FakeMouse()), loc) is False


def test_move_and_click_returns_false_when_box_raises(monkeypatch):
    """契约是"不抛异常"——点不到返回 False，让调用方兜底。"""
    monkeypatch.setattr("core.human_click.time.sleep", lambda *_: None)
    from core.human_click import move_and_click
    loc = FakeLoc(None, raise_on_box=True)
    assert move_and_click(FakePage(FakeMouse()), loc) is False


def test_move_and_click_returns_false_when_driver_down_fails(monkeypatch):
    monkeypatch.setattr("core.human_click.time.sleep", lambda *_: None)
    from core.human_click import move_and_click
    mouse = FakeMouse(fail_down=True)
    loc = FakeLoc({"x": 10, "y": 10, "width": 30, "height": 30})
    assert move_and_click(FakePage(mouse), loc) is False


def test_move_and_click_keeps_landing_point_inside_box(monkeypatch):
    """落点（最后一次 move）必须夹在元素内：贴边常被判定为非人工命中。

    注意只有落点受约束——曲线中间点本就该从元素外划入，否则就不是"曲线"了。
    """
    monkeypatch.setattr("core.human_click.time.sleep", lambda *_: None)
    import core.human_click as hc
    box = {"x": 0, "y": 0, "width": 10, "height": 10}
    mouse = FakeMouse()
    hc.move_and_click(FakePage(mouse), FakeLoc(box),
                      jitter=999)          # 极大抖动，压过夹取逻辑
    moves = [e for e in mouse.events if e[0] == "move"]
    assert len(moves) >= 2            # 起点 + 终点，说明确实走了曲线
    _, lx, ly = moves[-1]
    assert 2 <= lx <= 8 and 2 <= ly <= 8   # 距边留 2px 余量


def test_move_and_click_start_point_not_negative(monkeypatch):
    """起点被 max(0.0, …) 夹住——元素贴左上角时不该出现负起点。"""
    monkeypatch.setattr("core.human_click.time.sleep", lambda *_: None)
    import core.human_click as hc
    mouse = FakeMouse()
    hc.move_and_click(FakePage(mouse),
                      FakeLoc({"x": -50, "y": -50, "width": 20, "height": 20}))
    moves = [e for e in mouse.events if e[0] == "move"]
    assert moves
    _, sx, sy = moves[0]
    assert sx >= 0.0 and sy >= 0.0


# ---------------- 候选选择器 ----------------

def test_option_selectors_cover_byte_and_generic():
    """字节系 byte-select 与 antd/通用 li 都要覆盖到。"""
    joined = " ".join(OPTION_SELECTORS)
    assert "byte-select-option" in joined
    assert "[role=option]" in joined
    assert len(OPTION_SELECTORS) >= 3


def test_visible_options_builds_visible_selector():
    captured = {}

    class L:
        def __init__(self, sel):
            captured["sel"] = sel

    class P:
        def locator(self, sel):
            return L(sel)

    _visible_options(P())
    assert ":visible" in captured["sel"]
    for s in OPTION_SELECTORS:
        assert s in captured["sel"]


def test_visible_options_falls_back_on_error():
    """合并选择器失败时退到最朴素的 li:visible，不让下拉点击整体失败。"""
    calls = []

    class L:
        def __init__(self, sel):
            calls.append(sel)

    class P:
        def locator(self, sel):
            if ":visible" in sel and "byte-select" in sel:
                raise RuntimeError("unsupported selector")
            return L(sel)

    out = _visible_options(P())
    assert out is not None
    assert calls[-1] == "li:visible"