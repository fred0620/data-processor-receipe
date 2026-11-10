"""本機網頁工具的後端。只綁定 127.0.0.1，資料不會離開這台電腦。

已經內建、新增功能時要維持的：
- 只接受 Host 為本機的請求（擋 DNS rebinding），/api/ 擋跨站請求（擋 CSRF）。
- 回應加安全標頭；錯誤只回一般訊息，細節寫進 workspace/logs。
- 頁面全部關閉後自動結束；已經開著時再啟動，只開啟原本的頁面。
新增 API 時放在「功能」區塊，使用者資料只寫到 paths 定義的位置。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory
from werkzeug.exceptions import HTTPException

from . import __version__, logs, paths
from .logs import clean as log_text
from .logs import log

WEB = Path(__file__).resolve().parent / "web"
MAX_CLIENTS = 50
PORT_RANGE = 20
CLOSE_GRACE_SECONDS = 8          # 容許重新整理頁面，不會誤關
CLIENT_TIMEOUT_SECONDS = 1800    # 瀏覽器當掉、沒通知就消失時的上限
NO_CLIENT_TIMEOUT_SECONDS = 600  # 啟動後一直沒有開啟頁面
WATCH_SECONDS = 2
SLEEP_GAP_SECONDS = 30           # 檢查間隔突然變長，代表電腦剛從睡眠醒來

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; "
       "base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
HOME_ID = hashlib.sha256(str(paths.HOME).encode("utf-8")).hexdigest()[:16]  # 不把完整路徑（含使用者名稱）傳出去

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024

_clients: dict[str, float] = {}
_clients_lock = threading.Lock()
_jobs: dict[str, dict] = {}       # 背景工作；有未完成的工作時不會自動結束


class Missing(Exception):
    """找不到使用者要的東西，訊息會直接顯示在頁面上。"""


def _error(message: str, code: int = 400):
    return jsonify({"error": message}), code


def _json_body() -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValueError("請求內容格式不正確")
    return body


# ---------- 安全 ----------

def _is_local(netloc: str) -> bool:
    host = netloc.rsplit(":", 1)[0] if not netloc.endswith("]") else netloc
    return host.lower() in LOCAL_HOSTS


@app.before_request
def _guard():
    """本機服務也會被瀏覽器裡其他網站呼叫，這裡擋掉非本工具頁面發出的請求。"""
    if not _is_local(request.host):
        log.warning("拒絕請求：Host 不是本機 host=%s path=%s", log_text(request.host), log_text(request.path))
        return _error("只接受本機連線", 403)
    if not request.path.startswith("/api/"):
        return None
    site = request.headers.get("Sec-Fetch-Site")
    if site and site not in ("same-origin", "none"):
        log.warning("拒絕請求：跨站呼叫 site=%s path=%s", log_text(site), log_text(request.path))
        return _error("只接受本工具頁面發出的請求", 403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("Origin")
        if origin is not None and origin.split("://", 1)[-1] != request.host:
            log.warning("拒絕請求：來源不符 origin=%s path=%s", log_text(origin), log_text(request.path))
            return _error("只接受本工具頁面發出的請求", 403)
    return None


@app.after_request
def _headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if response.mimetype == "text/html":
        response.headers["Content-Security-Policy"] = CSP
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"  # 資料不留在瀏覽器快取
    return response


@app.errorhandler(Missing)
def _missing(exc):
    return _error(str(exc), 404)


@app.errorhandler(ValueError)
def _bad_value(exc):
    log.info("輸入不正確 path=%s：%s", log_text(request.path), log_text(exc, 300))
    return _error(str(exc))


@app.errorhandler(HTTPException)
def _http_error(exc):
    messages = {404: "找不到這個頁面", 405: "不支援這個操作", 413: "檔案太大，請分批加入"}
    return _error(messages.get(exc.code, "請求無法處理"), exc.code or 400)


@app.errorhandler(Exception)
def _unexpected(exc):
    """其他錯誤只回一般訊息，細節（含程式位置）只寫進本機日誌。"""
    log.error("處理請求時發生錯誤 path=%s", log_text(request.path), exc_info=exc)
    return _error("處理時發生錯誤，詳細內容已記錄在 workspace/logs", 500)


# ---------- 頁面與說明文件 ----------

@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/web/<path:name>")
def web_file(name):
    return send_from_directory(WEB, name)


@app.get("/manual")
def manual():
    return redirect(f"/docs/{paths.MANUAL.name}")


@app.get("/docs/<name>")
def guide(name):
    """使用手冊與換版說明。只開放固定的檔案，文件之間用相對連結互通。"""
    if name not in paths.GUIDES or not (paths.APP / name).exists():
        raise Missing("找不到這份說明")
    return send_from_directory(paths.APP, name)


@app.get("/api/ping")
def ping():
    """給第二次啟動判斷「工具是否已經開著」。"""
    return jsonify({"app": "dataprocessor", "home": HOME_ID})


@app.get("/api/status")
def status():
    return jsonify({"version": __version__})


@app.post("/api/heartbeat")
def heartbeat():
    client = request.args.get("client", "")
    if not re.fullmatch(r"[\w\-]{1,64}", client):
        raise ValueError("連線代號不正確")
    with _clients_lock:
        if client not in _clients and len(_clients) >= MAX_CLIENTS:
            return _error("開啟的頁面太多，請關閉一些分頁", 429)
        _clients[client] = time.time()
    return jsonify({"ok": True})


@app.post("/api/bye")
def bye():
    with _clients_lock:
        _clients.pop(request.args.get("client", ""), None)
    return jsonify({"ok": True})


# ---------- 功能：在這裡加上這個工具自己的 API ----------

@app.post("/api/example")
def example():
    """範例：回傳收到的文字。實作時換成真正的功能，日誌只記數量和代號，不記內容。"""
    body = _json_body()
    text = str(body.get("text", ""))[:1000]
    log.info("範例請求 length=%d", len(text))
    return jsonify({"echo": text})


# ---------- 啟動與自動結束 ----------

def _busy() -> bool:
    return any(not job.get("finished", True) for job in _jobs.values())


def _shutdown(reason: str) -> None:
    print(f"\n  {reason}，工具已關閉。\n", flush=True)
    log.info("關閉：%s", reason)
    shutil.rmtree(paths.UPLOADS, ignore_errors=True)
    os._exit(0)  # 結束整個行程，連接埠、檔案和記憶體都由系統回收


def _watch_clients() -> None:
    """所有頁面都關閉後自動結束，避免背景程式一直留著。"""
    started = last_tick = time.time()
    empty_since: float | None = None
    seen_client = False
    while True:
        time.sleep(WATCH_SECONDS)
        now = time.time()
        with _clients_lock:
            if now - last_tick > SLEEP_GAP_SECONDS:  # 睡眠期間頁面也無法回報，不算離線
                for client in _clients:
                    _clients[client] = now
            for client, seen in list(_clients.items()):
                if now - seen > CLIENT_TIMEOUT_SECONDS:
                    del _clients[client]
            seen_client = seen_client or bool(_clients)
            active = bool(_clients)
        last_tick = now
        if active or _busy():
            empty_since = None
            continue
        if not seen_client:
            if now - started > NO_CLIENT_TIMEOUT_SECONDS:
                _shutdown("沒有開啟頁面")
            continue
        empty_since = empty_since or now
        if now - empty_since >= CLOSE_GRACE_SECONDS:
            _shutdown("頁面已全部關閉")


def _port_is_free(port: int) -> bool:
    with socket.socket() as probe:
        if os.name != "nt":  # Windows 的這個選項會允許搶佔使用中的埠，不能設定
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _is_this_tool(port: int) -> bool:
    # 不走系統代理：公司電腦常設 HTTP_PROXY，會讓 127.0.0.1 的檢查失敗
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/ping", timeout=2) as response:
            data = json.loads(response.read())
    except (OSError, ValueError):
        return False
    return data.get("app") == "dataprocessor" and data.get("home") == HOME_ID


def _pick_port(start: int) -> tuple[int, bool]:
    """回傳 (埠, 工具是否已在這個埠上執行)。"""
    for port in range(start, start + PORT_RANGE):
        if _port_is_free(port):
            return port, False
        if _is_this_tool(port):
            return port, True
    raise OSError(f"連接埠 {start} 到 {start + PORT_RANGE - 1} 都被其他程式佔用")


def serve(port: int = 8765, open_browser: bool = True) -> None:
    paths.prepare()
    logs.setup(paths.LOGS)
    for attempt in range(3):
        chosen, running = _pick_port(port)
        url = f"http://127.0.0.1:{chosen}"
        if running:
            print(f"\n  工具已經開著，直接開啟 {url}\n", flush=True)
            if open_browser:
                webbrowser.open(url)
            return
        if attempt == 0:
            shutil.rmtree(paths.UPLOADS, ignore_errors=True)  # 清掉上次異常結束留下的暫存
        print(f"\n  資料處理器 {__version__} 已啟動：{url}\n  使用完畢後關閉瀏覽器頁面，或關閉這個視窗。\n", flush=True)
        log.info("啟動 version=%s port=%d", __version__, chosen)
        if open_browser:
            threading.Timer(0.8, webbrowser.open, args=(url,)).start()
            threading.Thread(target=_watch_clients, daemon=True).start()
        try:
            app.run(host="127.0.0.1", port=chosen, threaded=True)
            return
        except (OSError, SystemExit):  # 兩次啟動幾乎同時發生，等一下再判斷
            time.sleep(1)
    raise SystemExit("無法啟動工具，請關閉其他視窗後再試一次。")
