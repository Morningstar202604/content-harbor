# -*- coding: utf-8 -*-
"""AIGC 合规门禁回归——全项目风险最高却零直接覆盖的模块。

为什么优先测它：gate.py 是《人工智能生成合成内容标识办法》的落地实现
（显式标识 + 人审闸门），错了不是功能 bug 而是合规事故；而它此前只有
间接覆盖（/ai/gate 端点读开关），决策逻辑本身没有任何断言。

四道闸门：安全扫描 / AIGC 标识 / 双模型审查 / 发布闸门。
"""

import json

import pytest

from service.publishing import gate

LONG_SAFE = "这是一篇完全合规的技术文章，讲的是异步编程与协程调度。" * 30


def _art(source="ai", content=LONG_SAFE, **kw):
    a = {"title": "标题", "content_md": content, "source": source,
         "ext": "{}", "ai_model": "deepseek-chat"}
    a.update(kw)
    return a


@pytest.fixture(autouse=True)
def _no_config(monkeypatch, tmp_path):
    """把 config.json 指向不存在的路径，让门禁走默认（全开、无 REVIEW_MODEL）。
    否则测试会读到开发者本机真实的 config.json 而不稳定。"""
    monkeypatch.setattr(gate, "CONFIG_FILE", tmp_path / "no-such-config.json")


# ---------------- 开关 ----------------

def test_gate_enabled_by_default():
    assert gate.is_enabled() is True


@pytest.mark.parametrize("raw,expected", [
    (False, False), (True, True),
    ("false", False), ("False", False), ("FALSE", False),
    ("0", False), ("no", False), ("No", False),
    ("true", True), ("yes", True), ("1", True),
])
def test_is_enabled_parsing(monkeypatch, tmp_path, raw, expected):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"AIGC_GATE": raw}), encoding="utf-8")
    monkeypatch.setattr(gate, "CONFIG_FILE", cfg)
    assert gate.is_enabled() is expected


def test_corrupt_config_does_not_disable_gate(monkeypatch, tmp_path):
    """配置损坏时的默认必须是"开"——fail-safe 方向是拦住，不是放行。"""
    cfg = tmp_path / "config.json"
    cfg.write_text("{ 这不是合法 JSON", encoding="utf-8")
    monkeypatch.setattr(gate, "CONFIG_FILE", cfg)
    assert gate.is_enabled() is True


# ---------------- 1. 安全扫描 ----------------

@pytest.mark.parametrize("text,expected", [
    ("正常技术文章，没有任何问题", False),
    ("这篇讲了枪支交易", True),
    ("涉及法轮功", True),
    ("介绍六四事件", True),
    ("有代孕中介服务", True),
    ("钓鱼链接在这里", True),
    ("visit pornhub now", True),          # 正则
    ("buy pills online", True),           # 正则
    ("破解激活码出售", True),              # 正则
])
def test_scan_dangerous_true_positives(text, expected):
    assert bool(gate.scan_dangerous(text)) is expected


@pytest.mark.parametrize("text", [
    "pornography is a complex academic topic",   # 不该被 \b(pornhub|...)\b 命中
    "the online drug class in Python",           # 词序不匹配 buy+...+online
    "我们破解了密码学算法",                       # "破解" 后面不是卡密/激活码
    "本文讲 Python 的 dict 用法",
    "",
])
def test_scan_dangerous_no_false_positives(text):
    """误阳性会把正常技术文章全拦下，门禁就废了。"""
    assert gate.scan_dangerous(text) == []


def test_scan_dangerous_checks_title_too():
    """标题也是发布内容的一部分，只扫正文会漏。"""
    assert gate.scan_dangerous("正文很干净", title="赌博网站推荐") == ["赌博网站"]


def test_scan_dangerous_reports_all_hits():
    hits = gate.scan_dangerous("枪支交易与毒品制造")
    assert "枪支交易" in hits and "毒品制造" in hits


# ---------------- 2. AIGC 标识 ----------------

def test_add_aigc_label_writes_ext_fields():
    art = _art()
    out = gate.add_aigc_label(art, "deepseek-chat")
    ext = json.loads(out["ext"])
    assert ext["aigc"] is True
    assert ext["ai_model"] == "deepseek-chat"
    assert ext["aigc_at"] > 0


def test_add_aigc_label_appends_notice():
    out = gate.add_aigc_label(_art(), "m")
    assert "本文由 AI 辅助生成" in out["content_md"]
    assert out["content_md"].startswith(LONG_SAFE)


def test_add_aigc_label_is_idempotent():
    """重复打标不得堆叠多份声明——AI 改写会反复调用本函数。"""
    once = gate.add_aigc_label(_art(), "m")
    twice = gate.add_aigc_label(once, "m")
    assert twice["content_md"].count("本文由 AI 辅助生成") == 1


def test_add_aigc_label_preserves_existing_ext():
    art = _art()
    art["ext"] = json.dumps({"custom": "keep-me"})
    out = gate.add_aigc_label(art, "m")
    ext = json.loads(out["ext"])
    assert ext["custom"] == "keep-me"     # 不能被覆盖掉
    assert ext["aigc"] is True


def test_add_aigc_label_survives_corrupt_ext():
    art = _art()
    art["ext"] = "{坏的 JSON"
    out = gate.add_aigc_label(art, "m")
    assert json.loads(out["ext"])["aigc"] is True


def test_add_aigc_label_accepts_dict_ext():
    art = _art()
    art["ext"] = {"a": 1}
    out = gate.add_aigc_label(art, "m")
    assert json.loads(out["ext"])["a"] == 1


def test_add_aigc_label_falls_back_to_article_model():
    """model 参数为空时回退到文章自身的 ai_model。"""
    out = gate.add_aigc_label(_art(ai_model="gpt-4o"), "")
    assert json.loads(out["ext"])["ai_model"] == "gpt-4o"


def test_add_aigc_label_keeps_empty_when_both_empty():
    art = _art(ai_model="")
    out = gate.add_aigc_label(art, "")
    assert json.loads(out["ext"])["ai_model"] == ""


# ---------------- 3. 双模型审查 ----------------

def test_local_review_passes_clean_article():
    r = gate._local_review("标题", LONG_SAFE)
    assert r["verdict"] == "pass"
    assert r["reviewer"] == "local-heuristic"
    assert r["issues"] == []


def test_local_review_rejects_short_content():
    r = gate._local_review("标题", "太短了")
    assert r["verdict"] == "reject"
    assert any("篇幅过短" in i for i in r["issues"])


def test_local_review_rejects_unlabeled_code_block():
    """裸 ``` 开栏 = 未标语言。"""
    content = LONG_SAFE + "\n\n```\nprint(1)\n```"
    r = gate._local_review("标题", content)
    assert r["verdict"] == "reject"
    assert any("未标语言" in i for i in r["issues"])


def test_local_review_accepts_labeled_code_block():
    """回归：修复前的正则把闭栏 ``` 也当开栏，导致所有带代码块的文章被误判。"""
    content = LONG_SAFE + "\n\n```python\nprint(1)\n```"
    r = gate._local_review("标题", content)
    assert r["verdict"] == "pass"


@pytest.mark.parametrize("ph", ["TODO", "FIXME", "XXX", "lorem ipsum", "PLACEHOLDER"])
def test_local_review_rejects_placeholders(ph):
    """正文里的明显占位符（TODO/FIXME/lorem ipsum/placeholder）被 reject。

    回归：旧的检测器把 `{{ }}` 也当占位符，导致任何 Python f-string / Jinja / CSS 文章
    一跑就拒发（技术文档误报）。修复后只拦明确的人工标记，合法模板语法放行。
    """
    r = gate._local_review("标题", LONG_SAFE + f" {ph} ")
    assert r["verdict"] == "reject"
    assert any("占位符" in i for i in r["issues"])


def test_local_review_ignores_template_braces():
    """`{{ }}` 不在占位符黑名单里：合法模板语法不被误报。"""
    content = LONG_SAFE + "\n\nJinja 例子：`{{ name }}`，Python f-string: `{{ f'{x}' }}`"
    r = gate._local_review("标题", content)
    assert r["verdict"] == "pass", r["issues"]


def test_local_review_placeholder_inside_code_block_ignored():
    """代码块内的 `TODO` 不当作占位符残留（注释里的 TODO 完全合法）。"""
    content = LONG_SAFE + "\n\n```python\n# TODO: 这里可以优化\nprint(1)\n```"
    r = gate._local_review("标题", content)
    assert r["verdict"] == "pass", r["issues"]


def test_dual_review_uses_local_when_no_review_model():
    r = gate.dual_model_review(_art("human"))
    assert r["reviewer"] == "local-heuristic"


def test_safety_scan_runs_before_review_model(monkeypatch, tmp_path):
    """高危内容必须在任何审查之前就被拦，配了 REVIEW_MODEL 也不能绕过。"""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"REVIEW_MODEL": "gpt-4o"}), encoding="utf-8")
    monkeypatch.setattr(gate, "CONFIG_FILE", cfg)

    called = []
    monkeypatch.setattr("service.publishing.ai.chat",
                        lambda *a, **k: called.append(1) or '{"verdict":"pass","issues":[]}')

    r = gate.dual_model_review(_art("human", LONG_SAFE + " 涉及枪支交易"))
    assert r["verdict"] == "reject"
    assert r["reviewer"] == "safety-scan"
    assert not called          # 二审压根没被调用


def test_dual_review_calls_llm_when_configured(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"REVIEW_MODEL": "openai:gpt-4o"}), encoding="utf-8")
    monkeypatch.setattr(gate, "CONFIG_FILE", cfg)
    monkeypatch.setattr("service.publishing.ai.chat",
                        lambda *a, **k: '结果：{"verdict":"reject","issues":["口径不妥"]}')

    r = gate.dual_model_review(_art("human"))
    assert r["verdict"] == "reject"
    assert r["issues"] == ["口径不妥"]
    assert r["reviewer"] == "dual-model:openai:gpt-4o"


def test_dual_review_degrades_to_local_when_llm_fails(monkeypatch, tmp_path):
    """LLM 挂了必须降级本地，不能让审查整体失效后放行。"""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"REVIEW_MODEL": "openai:gpt-4o"}), encoding="utf-8")
    monkeypatch.setattr(gate, "CONFIG_FILE", cfg)

    def boom(*a, **k):
        raise RuntimeError("API 502")

    monkeypatch.setattr("service.publishing.ai.chat", boom)
    r = gate.dual_model_review(_art("human"))
    assert r["reviewer"] == "fallback-local"
    assert r["verdict"] == "pass"          # 本地判定干净
    assert any("降级本地" in i for i in r["issues"])


def test_dual_review_degrade_is_not_silent_pass(monkeypatch, tmp_path):
    """降级本身必须留痕，否则"降级通过"和"二审通过"无法区分。"""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"REVIEW_MODEL": "x"}), encoding="utf-8")
    monkeypatch.setattr(gate, "CONFIG_FILE", cfg)
    monkeypatch.setattr("service.publishing.ai.chat",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = gate.dual_model_review(_art("human"))
    assert r["issues"], "降级必须留下可追溯的 issues"


# ---------------- 4. 发布闸门 ----------------

def test_ai_source_blocked_from_live_publish():
    """法规核心：AI 源内容禁止直接上线，必须先草稿 + 人工确认。"""
    r = gate.gate_publish(_art("ai"), draft_only=False)
    assert r["approved"] is False
    assert any("人工确认" in i for i in r["issues"])


def test_ai_source_allowed_as_draft():
    r = gate.gate_publish(_art("ai"), draft_only=True)
    assert r["approved"] is True
    assert r["aigc_labeled"] is True


def test_human_source_can_publish_live():
    r = gate.gate_publish(_art("human"), draft_only=False)
    assert r["approved"] is True
    assert r["aigc_labeled"] is False


def test_gate_rejects_dangerous_content_even_as_draft():
    r = gate.gate_publish(_art("ai", LONG_SAFE + " 含枪支交易"), draft_only=True)
    assert r["approved"] is False
    assert any("高危内容" in i for i in r["issues"])


def test_gate_off_short_circuits_everything(monkeypatch, tmp_path):
    """门禁关闭后应直接放行且不做审查——这是显式的、有记录的降级。"""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"AIGC_GATE": False}), encoding="utf-8")
    monkeypatch.setattr(gate, "CONFIG_FILE", cfg)

    r = gate.gate_publish(_art("ai", "含枪支交易"), draft_only=False)
    assert r["approved"] is True
    assert r["review"]["reviewer"] == "gate-off"
    assert r["aigc_labeled"] is False


def test_apply_gate_raises_on_reject():
    with pytest.raises(gate.GateError) as ei:
        gate.apply_gate_before_publish(_art("ai"), draft_only=False)
    assert "人工确认" in str(ei.value)


def test_apply_gate_labels_ai_source_on_approve():
    out = gate.apply_gate_before_publish(_art("ai"), draft_only=True)
    art = out["article"]
    assert json.loads(art["ext"])["aigc"] is True
    assert "本文由 AI 辅助生成" in art["content_md"]


def test_apply_gate_does_not_label_human_source():
    out = gate.apply_gate_before_publish(_art("human"), draft_only=False)
    assert json.loads(out["article"]["ext"]) == {}
    assert "本文由 AI 辅助生成" not in out["article"]["content_md"]


def test_apply_gate_error_message_not_empty():
    """GateError 的消息会进 jobs 表供追溯，不能是空串。"""
    with pytest.raises(gate.GateError) as ei:
        gate.apply_gate_before_publish(_art("ai"), draft_only=False)
    assert str(ei.value).strip()