# -*- coding: utf-8 -*-
"""内容质检引擎回归：零外部依赖的纯函数，最适合当行为契约锁。"""

from service.publishing import content_qa as qa

GOOD_MD = """# Python 异步编程入门指南

异步编程是 Python 高并发场景的核心技术。本文从事件循环讲起，逐步深入到
协程、任务与实战模式，帮助读者建立完整的知识框架。

## 为什么需要异步

在高并发场景下，传统同步阻塞会让每个请求占用一个线程。线程数量上来之后，
上下文切换的开销会成为瓶颈。异步通过事件循环把等待时间还回去。

## 事件循环是什么

事件循环是异步程序的调度中枢。它不停地从任务队列里取出就绪任务执行，
遇到 IO 等待时挂起当前任务，转去处理别的任务。

## 协程与任务

协程是可以用 `await` 挂起的函数。把协程交给事件循环调度，就成了任务。
任务之间可以并发推进，这是异步提升吞吐的根本原因。

## 实战建议

第一，不要混用阻塞调用。第二，合理设置超时。第三，用信号量限制并发数。
"""


def test_strip_md_removes_markup():
    text = "# 标题\n\n`code` 与 [链接](http://x) 与 ![图](a.png) 正文"
    out = qa._strip_md(text)
    assert "#" not in out
    assert "`" not in out
    assert "链接" in out and "图" in out and "正文" in out


def test_readability_scores_well_formed_article():
    r = qa.readability_score(GOOD_MD)
    assert 0 <= r["score"] <= 100
    assert r["score"] >= 60


def test_readability_rejects_too_short():
    r = qa.readability_score("太短了")
    assert r["score"] == 0
    assert r["label"] == "太短"


def test_seo_rewards_title_summary_tags_and_h2():
    long_summary = "这是一段足够长度的摘要，用来覆盖摘要字数区间加分项，" * 3
    r = qa.seo_score("Python 异步编程入门指南", GOOD_MD,
                     summary=long_summary, tags="python,异步,协程")
    assert r["score"] >= 70
    assert r["label"] in ("优秀", "良好")


def test_seo_penalizes_missing_summary_and_tags():
    r = qa.seo_score("题", GOOD_MD, summary="", tags="")
    tips = " ".join(r["tips"])
    assert "缺少摘要" in tips
    assert "缺少标签" in tips
    assert r["score"] < 50


def test_seo_score_is_clamped():
    r = qa.seo_score("# 标题 " * 40, GOOD_MD, summary="S", tags="a")
    assert 0 <= r["score"] <= 100


def test_minhash_jaccard_identity_and_disjoint():
    a = qa._shingles(GOOD_MD)
    b = qa._shingles(GOOD_MD)
    c = qa._shingles("完全不相干的另一段文字内容，讲的是做菜和烘焙技巧。")
    assert qa._jaccard(qa._minhash(a), qa._minhash(b)) == 1.0
    assert qa._jaccard(qa._minhash(a), qa._minhash(c)) < 0.3


def test_check_similarity_finds_duplicate_and_skips_self():
    others = [
        {"id": 2, "title": "旧文", "content_md": GOOD_MD},
        {"id": 3, "title": "无关", "content_md": "烘焙入门：先准备面粉和烤箱。"},
        {"id": 4, "title": "空文", "content_md": ""},
    ]
    sim = qa.check_similarity(GOOD_MD, others, threshold=0.3)
    assert [s["id"] for s in sim] == [2]
    assert sim[0]["similarity"] >= 0.3


def test_empty_corpus_yields_no_similarity():
    assert qa.check_similarity(GOOD_MD, []) == []


def test_full_qa_penalizes_duplicates():
    article = {"title": "Python 异步编程入门指南", "content_md": GOOD_MD,
               "summary": "摘要" * 30, "tags": "python,异步"}
    clean = qa.full_qa(article, other_articles=[])
    dup = qa.full_qa(article, other_articles=[
        {"id": 9, "title": "旧文", "content_md": GOOD_MD}])
    assert dup["duplicates"]
    assert dup["total"] < clean["total"]
    assert any("相似度" in t for t in dup["tips"])


def test_full_qa_shape():
    out = qa.full_qa({"title": "T", "content_md": GOOD_MD})
    for k in ("total", "label", "readability", "seo", "duplicates", "tips"):
        assert k in out
    assert 0 <= out["total"] <= 100
