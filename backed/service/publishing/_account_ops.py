# -*- coding: utf-8 -*-
"""账号操作（登录 / 登出 / 辅助 / 验证码）的具体实现——从 ``service.py`` Hub 抽出。

抽出动机：``service.py`` Hub 承担文章 CRUD / 发布编排 / 登录管理 / AI 四大职责，
登录态管理（浏览器实例、profile 目录、验证码、二维码）这一块独立抽出后：
  - Hub 瘦身为纯编排入口（路由 → 握手 → 调用）
  - 登录逻辑可独立单测（mock pool 即可）
  - 浏览器路径/验证码策略变更不用碰发布链路

本层是**函数式**实现，依赖由调用方注入：
  - ``pool``  : BrowserPoolManager 实例
  - ``_drop`` : callable(platform, account) → None
  - ``_busy`` : contextmanager(platform, account)
  - ``db_conn``: SQLite connection
  - ``demo``  : bool (演示模式短路)
所有函数都是无副作用操作（除了 DB 写和浏览器启动），便于组合测试。"""

import shutil
import threading
import time
from pathlib import Path

from service.publishing.adapters.base import PlatformError, get_adapter

ROOT = Path(__file__).resolve().parent.parent


def login(platform, account, timeout, on_captcha, pool, _drop, _busy, db_conn, demo):
    """登录主流程：纯协议平台验凭据；其它平台开浏览器走 ensure_login。"""
    if demo:
        from service.publishing import db
        db.upsert_account(db_conn, platform, account, "-", "logined")
        return True, "演示模式：模拟登录成功"

    ad = get_adapter(platform)
    if not ad.needs_browser:
        return login_api_only(platform, account, ad, db_conn)

    return login_browser(platform, account, timeout, on_captcha, pool, _drop, _busy, db_conn)


def login_api_only(platform, account, ad, db_conn):
    """纯协议平台登录：验凭据 + 写库。"""
    from service.publishing import db
    try:
        ok = ad.check_auth(None)
    except PlatformError:
        ok = False
    db.upsert_account(db_conn, platform, account, "-",
                        "logined" if ok else "offline")
    return ok, ("凭据有效（免登录 API）" if ok else "凭据无效，检查 config.json")


def login_browser(platform, account, timeout, on_captcha, pool, _drop, _busy, db_conn):
    """浏览器登录：持 per-key 互斥 → 释放旧实例 → 开有头浏览器 → ensure_login。"""
    from service.publishing.browser import BuiltinBrowser, browser_thread_run, ensure_login
    from service.publishing import db

    with _busy(platform, account):
        _drop(platform, account)

        def _op():
            br = BuiltinBrowser(platform, account, headless=False)
            try:
                ok, msg = ensure_login(br, get_adapter(platform).login_url,
                                       get_adapter(platform).check_auth,
                                       timeout=timeout,
                                       on_captcha=on_captcha)
                if ok:
                    try:
                        br.export_auth()
                    except Exception:
                        pass
                db.upsert_account(db_conn, platform, account,
                                  str(br.profile_dir), "logined" if ok else "offline")
                return ok, msg
            finally:
                br.close()
        return browser_thread_run(_op)


def logout(platform, account, pool, _drop, db_conn):
    """清除登录态：踢池 → 删 profile 目录 + auth 快照 → DB 置离线。"""
    _drop(platform, account)
    from service.publishing.browser import PROFILE_ROOT
    removed = []
    profile_dir = PROFILE_ROOT / f"{platform}_{account}"
    auth_file = PROFILE_ROOT / f"{platform}_{account}.auth.json"
    if profile_dir.exists():
        shutil.rmtree(profile_dir, ignore_errors=True)
        removed.append(str(profile_dir))
    if auth_file.exists():
        auth_file.unlink(missing_ok=True)
        removed.append(str(auth_file))
    db_conn.execute(
        "UPDATE accounts SET status='offline', last_check=? WHERE platform=? AND name=?",
        (time.time(), platform, account))
    db_conn.commit()
    return {"platform": platform, "removed": removed,
            "note": "登录态已清除，下次登录需重新扫码"}


def solve_captcha(platform, account, wait, pool, _drop, _busy, db_conn):
    """弹验证码就地处理：先半自动，不行转人工。"""
    from service.publishing.browser import (BuiltinBrowser, browser_thread_run,
                                             CaptchaPolicy, wait_human_captcha)

    ad = get_adapter(platform)
    if not ad.needs_browser:
        return {"ok": True, "msg": f"{platform} 走免登 API，不会有验证码"}

    _drop(platform, account)

    def _op():
        br = BuiltinBrowser(platform, account, headless=False)
        try:
            page = br.new_page()
            page.goto(ad.login_url, timeout=60000, wait_until="domcontentloaded")
            time.sleep(3)
            kind = CaptchaPolicy.detect(page)
            if not kind:
                return {"ok": True, "msg": "当前页面没有验证码"}
            ok, info = wait_human_captcha(page, platform, timeout=wait)
            return {"ok": ok, "kind": kind, **info}
        finally:
            br.close()
    return browser_thread_run(_op)


def assist_open(platform, account, url, timeout, pool, _drop, _busy, demo, db_conn):
    """带登录态的有头浏览器打开平台页。"""
    if demo:
        return {"ok": True, "msg": "演示模式：模拟打开平台页（带登录态）"}

    from service.publishing.browser import BuiltinBrowser, browser_thread_run
    with _busy(platform, account):
        _drop(platform, account)

        def _op():
            br = BuiltinBrowser(platform, account, headless=False)
            closed = threading.Event()
            try:
                ctx = br.start()
                page = ctx.new_page()
                page.on("close", lambda _: closed.set())
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                closed.wait(timeout=timeout)
                msg = ("平台页已关闭——如已完成操作，回管理页点「已处理，恢复」"
                       if closed.is_set() else f"assist 超时({timeout}s)自动关闭")
                return {"ok": True, "msg": msg}
            finally:
                try:
                    br.close()
                except Exception:
                    pass
        return browser_thread_run(_op)
