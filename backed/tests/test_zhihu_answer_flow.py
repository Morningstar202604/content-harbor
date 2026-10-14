# -*- coding: utf-8 -*-
"""知乎「回答问题」链路回归（2026-10-14）。

不触网：假 page 按 JS 哨兵分派；_import_md_file 打桩（导入机制由真机探针实测 + 专栏链路既有测试覆盖）。
覆盖：路由分流、正文回读纪律、draft_only、发布验证双通道、失败路径抛错。
"""
import pytest

from service.publishing.adapters import zhihu as zh
from service.publishing.adapters.base import PlatformError

QURL = "https://www.zhihu.com/question/2088198385572526079"
MD = "标题行\n\n这是一段足够长的正文，用于内容证据比对，第二句让片段有区分度。"


class _StubLocatorClick:
    """模拟被顶栏拦截的 locator.click —— 必须抛错走 JS click 降级。"""

    @property
    def first(self):
        return self

    def click(self, *a, **kw):
        raise RuntimeError("intercepts pointer events")


class FakePage:
    def __init__(self, *, editor_opens=True, body=MD, url=QURL,
                 publish_done_by_url=False, publish_done_by_marker=True):
        self.editor_opens = editor_opens
        self.body = body
        self.url = url
        self.publish_done_by_url = publish_done_by_url
        self.publish_done_by_marker = publish_done_by_marker
        self.write_clicked = False
        self.publish_clicked = False

    def goto(self, url, **kw):
        self.url = url
        return None

    def evaluate(self, js, arg=None):
        if "WriteAnswerButton" in js:
            self.write_clicked = True
            return self.editor_opens
        if "data-contents" in js and "innerText" in js and "length" in js:  # READY_JS
            return len(self.body) if self.editor_opens else -1
        if "hub:read-state" in js:
            return {"body": self.body, "title": ""}
        if "发布回答" in js:            # _click_answer_publish 的 JS 通道
            self.publish_clicked = True
            if self.publish_done_by_url:
                self.url = f"{QURL}/answer/123456789"
            return True
        if "修改回答" in js:            # 发布完成标记轮询
            return self.publish_done_by_marker
        return None

    def locator(self, *a, **kw):
        return _StubLocatorClick()


class _FastClock:
    """轮询用时钟桩：sleep 不真睡、time 每次前跳 10s（一轮就超出 deadline）。"""

    def __init__(self):
        self.t = 0.0

    def time(self):
        self.t += 10.0
        return self.t

    def sleep(self, *_a, **_k):
        return None


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(zh, "time", _FastClock())
    monkeypatch.setattr(zh.ZhihuAdapter, "save_debug",
                        lambda self, page, tag: "skipped")


def _adapter(monkeypatch):
    ad = zh.ZhihuAdapter()
    monkeypatch.setattr(zh.ZhihuAdapter, "_import_md_file",
                        lambda self, page, content: True)
    monkeypatch.setattr(zh.ZhihuAdapter, "_inject_editor",
                        lambda self, page, content: None)
    return ad


def test_question_url_routes_to_answer_flow(monkeypatch):
    """settings.zhihu.question_url 给了 → publish() 分流到回答链路。"""
    ad = zh.ZhihuAdapter()
    called = {}

    def _fake_answer(self, page, article, url, options):
        called["url"] = url
        return {"post_id": "x", "post_url": url, "draft_only": False}

    monkeypatch.setattr(zh.ZhihuAdapter, "publish_as_answer", _fake_answer)
    r = ad.publish(FakePage(), {"content_md": MD}, {"question_url": QURL})
    assert called["url"] == QURL
    assert r["post_id"] == "x"


def test_answer_happy_path_url_verify(monkeypatch):
    ad = _adapter(monkeypatch)
    page = FakePage(publish_done_by_url=True)
    r = ad.publish_as_answer(page, {"content_md": MD}, QURL)
    assert page.write_clicked and page.publish_clicked
    assert r["post_id"] == "123456789"
    assert r["post_url"].endswith("/answer/123456789")
    assert r["draft_only"] is False


def test_answer_happy_path_marker_verify(monkeypatch):
    """发布后 URL 不变但出现「修改回答」也算发布完成（双通道验证）。"""
    ad = _adapter(monkeypatch)
    page = FakePage(publish_done_by_url=False, publish_done_by_marker=True)
    r = ad.publish_as_answer(page, {"content_md": MD}, QURL)
    assert page.publish_clicked
    assert r["post_id"] == ""
    assert r["post_url"] == QURL


def test_answer_readback_mismatch_raises(monkeypatch):
    """回读证不出正文 → 不点发布，直接抛（绝不让旧/空正文上线）。"""
    ad = _adapter(monkeypatch)
    page = FakePage(body="完全无关的另一段内容，和注入的目标毫无关系")
    with pytest.raises(PlatformError) as ei:
        ad.publish_as_answer(page, {"content_md": MD}, QURL)
    assert "回答正文注入" in str(ei.value)
    assert page.publish_clicked is False


def test_answer_editor_not_open_raises(monkeypatch):
    ad = _adapter(monkeypatch)
    page = FakePage(editor_opens=False)
    with pytest.raises(PlatformError) as ei:
        ad.publish_as_answer(page, {"content_md": MD}, QURL)
    assert "编辑器未打开" in str(ei.value)


def test_answer_draft_only_no_publish(monkeypatch):
    ad = _adapter(monkeypatch)
    page = FakePage()
    r = ad.publish_as_answer(page, {"content_md": MD}, QURL, {"draft_only": True})
    assert r["draft_only"] is True
    assert page.publish_clicked is False


def test_answer_publish_stuck_raises(monkeypatch):
    """点了发布但 URL 无 /answer/ 且无「修改回答」→ 判定未发布成功。"""
    ad = _adapter(monkeypatch)
    page = FakePage(publish_done_by_url=False, publish_done_by_marker=False)
    with pytest.raises(PlatformError) as ei:
        ad.publish_as_answer(page, {"content_md": MD}, QURL)
    assert "未观察到发布完成" in str(ei.value)
