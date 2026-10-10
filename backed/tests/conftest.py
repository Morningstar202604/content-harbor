# -*- coding: utf-8 -*-
"""测试公共夹具：把一切落盘副作用关进 tmp_path。

项目真实数据落在 `backed/data/hub.db`（gitignore），测试绝不能碰它——
否则跑一次测试就把开发库改了。这里在导入被测模块后把路径常量指到
临时目录，并对只读不写的地方做无害化替换。
"""

import sys
from pathlib import Path

import pytest

BACKED_ROOT = Path(__file__).resolve().parents[1]
if str(BACKED_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKED_ROOT))

from service.publishing import db, events, observability as obs  # noqa: E402
from service.publishing import _webhook_store as _wh  # noqa: E402


class _NullLogger:
    """吞掉结构化事件日志，不在测试机上乱写 data/observability/。"""

    def info(self, *args, **kwargs):
        pass

    warning = info
    error = info
    debug = info
    exception = info


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    """隔离 DB 路径 / 事件日志 / webhook 派发线程。"""
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "observability").mkdir(parents=True, exist_ok=True)
    db_file = data / "hub.db"

    monkeypatch.setattr(db, "DB_PATH", db_file)
    monkeypatch.setattr(_wh, "_DB_PATH", db_file)
    monkeypatch.setattr(obs, "EVENT_LOG", data / "observability" / "events.log")
    monkeypatch.setattr(obs, "_event_logger", _NullLogger())

    # webhook 派发线程是模块导入时拉起来的守护线程，测试里不发真实 HTTP
    events.stop_dispatcher()

    yield {"data": data, "db_file": db_file, "root": tmp_path}


@pytest.fixture
def conn(sandbox):
    """一条指向临时库的连接，带齐 SCHEMA + 迁移。"""
    c = db.connect(sandbox["db_file"])
    yield c
    c.close()
