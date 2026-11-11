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
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException

from . import __version__, engine, logs, paths
from .engine.explain import explain
from .engine.trace import trace
from .engine.export import export as export_excel
from .engine.recipe import RECIPE_ID
from .engine.review import MappingStore, ReviewStore
from .engine.textnorm import parse_date, parse_integer, parse_number
from .engine.workbook import read_workbook
from .logs import clean as log_text
from .logs import log

WEB = Path(__file__).resolve().parent / "web"
MAX_CLIENTS = 50
PORT_RANGE = 20
CLOSE_GRACE_SECONDS = 8          # 容許重新整理頁面，不會誤關
LIVE_PING_SECONDS = 5            # 頁面連線的保持訊號間隔；瀏覽器關掉後最晚這麼久會發現
CLIENT_TIMEOUT_SECONDS = 180     # 沒有保持連線、只靠 heartbeat 的頁面，多久沒消息就當作已關閉
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
_live: dict[str, int] = {}        # 保持連線中的頁面 → 連線數
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
    log.info("輸入不正確 path=%s", log_text(request.path))   # 訊息可能含使用者輸入的值，不寫進日誌
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


@app.get("/api/live")
def live():
    """頁面開著時保持一條連線（Server-Sent Events）。

    瀏覽器整個關掉、當掉或直接結束時，頁面來不及通知 /api/bye，但這條連線一定會斷：
    下一次送保持訊號時寫入失敗，就知道這個頁面已經不在了。背景分頁的計時器會被瀏覽器放慢，
    連線不會，所以不靠 heartbeat 判斷。"""
    client = request.args.get("client", "")
    if not re.fullmatch(r"[\w\-]{1,64}", client):
        raise ValueError("連線代號不正確")
    with _clients_lock:
        if client not in _clients and len(_clients) >= MAX_CLIENTS:
            return _error("開啟的頁面太多，請關閉一些分頁", 429)
        _clients[client] = time.time()
        _live[client] = _live.get(client, 0) + 1

    def stream():
        try:
            yield "retry: 3000\n\n"
            while True:
                time.sleep(LIVE_PING_SECONDS)
                yield ": ping\n\n"
                with _clients_lock:
                    _clients[client] = time.time()
        finally:  # 連線斷了（頁面關閉、瀏覽器結束）
            with _clients_lock:
                _live[client] -= 1
                if _live[client] <= 0:
                    del _live[client]
                    _clients.pop(client, None)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/api/bye")
def bye():
    with _clients_lock:
        _clients.pop(request.args.get("client", ""), None)
    return jsonify({"ok": True})


# ---------- 功能：在這裡加上這個工具自己的 API ----------

RECIPE_LIMIT = 512 * 1024
MAX_RUNS = 10
MAX_WORKBOOKS = 10
_workbooks: dict[str, dict] = {}   # 代號 → 上傳的 workbook
_runs: dict[str, dict] = {}        # 代號 → 最近一次執行結果
_run_lock = threading.Lock()
UNSAFE_NAME = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')


def _safe_name(raw: str | None, limit: int = 120) -> str:
    """只保留檔名本身，去掉路徑、控制字元與 Windows 不允許的字元。"""
    name = Path((raw or "").replace("\\", "/")).name
    name = UNSAFE_NAME.sub("_", name).strip(" .")
    return name[:limit] or "file"


def _recipe_path(recipe_id: str) -> Path:
    if not RECIPE_ID.fullmatch(recipe_id or ""):
        raise Missing("找不到這份 recipe")
    path = paths.RECIPES / f"{recipe_id}.yaml"
    if not path.is_file():
        raise Missing("找不到這份 recipe")
    return path


def _read_recipe(recipe_id: str):
    return engine.load_recipe(_recipe_path(recipe_id).read_text(encoding="utf-8"))


def _recipe_problem(exc: engine.RecipeError):
    return jsonify({"error": "recipe 有問題，請修正後再試", "problems": exc.problems}), 422


@app.get("/api/recipes")
def list_recipes():
    items = []
    for path in sorted(paths.RECIPES.glob("*.yaml")):
        item = {"id": path.stem, "name": path.stem, "description": "", "problems": []}
        try:
            recipe = engine.load_recipe(path.read_text(encoding="utf-8"))
            item.update(id=recipe.id, name=recipe.name, description=recipe.description)
            if recipe.id != path.stem:
                item["problems"] = [f"檔名 {path.stem}.yaml 和 id「{recipe.id}」不同，請把兩者改成一樣"]
        except engine.RecipeError as exc:
            item["problems"] = exc.problems
        except (OSError, UnicodeDecodeError):
            item["problems"] = ["無法讀取這個檔案，請確認是 UTF-8 文字檔"]
        items.append(item)
    return jsonify({"recipes": items})


@app.get("/api/spec")
def recipe_spec():
    """recipe 規格全文，讓使用者複製給 AI。"""
    return jsonify({"text": paths.RECIPE_SPEC.read_text(encoding="utf-8")})


@app.get("/api/recipes/<recipe_id>/explain")
def explain_saved(recipe_id):
    """把已存的 recipe 翻成白話說明。"""
    try:
        return jsonify(explain(_read_recipe(recipe_id)))
    except engine.RecipeError as exc:
        return _recipe_problem(exc)


@app.post("/api/recipes/explain")
def explain_draft():
    """還沒存的 recipe 先預覽說明；有問題時回傳問題清單。"""
    text = str(_json_body().get("text", ""))
    if len(text.encode("utf-8")) > RECIPE_LIMIT:
        raise ValueError("recipe 太大（上限 512 KB）")
    try:
        return jsonify(explain(engine.load_recipe(text)))
    except engine.RecipeError as exc:
        return _recipe_problem(exc)


@app.get("/api/recipes/<recipe_id>")
def get_recipe(recipe_id):
    return jsonify({"id": recipe_id, "text": _recipe_path(recipe_id).read_text(encoding="utf-8")})


@app.post("/api/recipes")
def save_recipe():
    """存 recipe：可以上傳 .yaml 檔，或貼上文字。存檔前先完整檢查，不合格的不存。"""
    upload = request.files.get("file")
    if upload is not None:
        data = upload.read(RECIPE_LIMIT + 1)
    else:
        data = str(_json_body().get("text", "")).encode("utf-8")
    if len(data) > RECIPE_LIMIT:
        raise ValueError("recipe 太大（上限 512 KB）")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("recipe 要是 UTF-8 文字檔") from None
    try:
        recipe = engine.load_recipe(text)
    except engine.RecipeError as exc:
        log.info("recipe 檢查不通過 problems=%d", len(exc.problems))
        return _recipe_problem(exc)
    paths.RECIPES.mkdir(parents=True, exist_ok=True)
    (paths.RECIPES / f"{recipe.id}.yaml").write_text(text.replace("\r\n", "\n"), encoding="utf-8")
    log.info("儲存 recipe id=%s", log_text(recipe.id))
    return jsonify({"id": recipe.id, "name": recipe.name})


@app.delete("/api/recipes/<recipe_id>")
def delete_recipe(recipe_id):
    _recipe_path(recipe_id).unlink()
    log.info("刪除 recipe id=%s", log_text(recipe_id))
    return jsonify({"ok": True})


def _register_workbook(source: Path, name: str) -> dict:
    sheets = read_workbook(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    workbook_id = uuid.uuid4().hex[:12]
    _workbooks[workbook_id] = {"path": source, "name": name, "hash": digest, "sheets": sheets}
    while len(_workbooks) > MAX_WORKBOOKS:   # 只留最近幾份，舊的上傳檔一併刪除
        old = _workbooks.pop(next(iter(_workbooks)))
        if old["path"].parent == paths.UPLOADS:
            old["path"].unlink(missing_ok=True)
    log.info("載入 workbook id=%s sheets=%d", workbook_id, len(sheets))
    return {"id": workbook_id, "name": name,
            "sheets": [{"name": s.name, "rows": len(s.rows)} for s in sheets]}


@app.post("/api/workbooks")
def upload_workbook():
    upload = request.files.get("file")
    if upload is None:
        raise ValueError("請選擇 Excel 檔案")
    name = _safe_name(upload.filename)
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise ValueError("只支援 .xlsx 或 .xlsm；舊的 .xls 請先另存成 .xlsx")
    head = upload.stream.read(4)
    upload.stream.seek(0)
    if head != b"PK\x03\x04":
        raise ValueError("這不是有效的 Excel 檔案")
    paths.UPLOADS.mkdir(parents=True, exist_ok=True)
    target = paths.UPLOADS / f"{uuid.uuid4().hex[:8]}_{name}"
    upload.save(target)
    try:
        return jsonify(_register_workbook(target, name))
    except Exception as exc:
        target.unlink(missing_ok=True)
        if isinstance(exc, ValueError):
            raise
        log.warning("無法讀取 workbook", exc_info=exc)
        raise ValueError("無法讀取這個 Excel 檔案，可能已損毀或有密碼保護") from None


@app.get("/api/samples")
def list_samples():
    return jsonify({"samples": [p.name for p in sorted(paths.SAMPLES.glob("*.xlsx"))]})


@app.post("/api/samples/<name>")
def use_sample(name):
    path = paths.SAMPLES / _safe_name(name)
    if not path.is_file() or path.suffix.lower() != ".xlsx":
        raise Missing("找不到這份範例")
    return jsonify(_register_workbook(path, path.name))


def _execute(run_id: str) -> dict:
    record = _runs[run_id]
    workbook = _workbooks.get(record["workbook"])
    if workbook is None:
        raise Missing("檔案已關閉，請重新上傳")
    try:
        recipe = _read_recipe(record["recipe"])
    except engine.RecipeError as exc:
        raise _RecipeInvalid(exc) from None
    review = ReviewStore(paths.REVIEWS, recipe.id, workbook["hash"])
    mappings = MappingStore(paths.MAPPINGS, recipe.id)
    _jobs[run_id] = {"finished": False}
    started = time.time()
    try:
        keep: dict = {}
        with _run_lock:
            result = engine.run(recipe, workbook["sheets"], review, mappings, paths.SCRATCH, keep)
    finally:
        _jobs[run_id]["finished"] = True
    result["run_id"] = run_id
    result["workbook"] = {"id": record["workbook"], "name": workbook["name"]}
    result["decisions"] = review.count()               # 人工決定的數量，重設前讓使用者知道會清掉多少
    result["can_restore"] = review.backup.exists()     # 剛重設過，可以復原
    record.update(result=result, review=review, job=keep.get("job"))   # job 是執行紀錄，覆核某一列時用
    log.info("執行 run=%s recipe=%s status=%s rows=%d issues=%d seconds=%.1f", run_id, log_text(recipe.id),
             result["status"], len(result["output"]["rows"]), result["counts"]["review"], time.time() - started)
    return result


class _RecipeInvalid(Exception):
    def __init__(self, error: engine.RecipeError):
        self.error = error


@app.errorhandler(_RecipeInvalid)
def _recipe_invalid(exc):
    return _recipe_problem(exc.error)


@app.post("/api/runs")
def start_run():
    body = _json_body()
    recipe_id = str(body.get("recipe", ""))
    workbook_id = str(body.get("workbook", ""))
    _recipe_path(recipe_id)
    if workbook_id not in _workbooks:
        raise Missing("檔案已關閉，請重新上傳")
    run_id = uuid.uuid4().hex[:12]
    _runs[run_id] = {"recipe": recipe_id, "workbook": workbook_id}
    while len(_runs) > MAX_RUNS:
        _runs.pop(next(iter(_runs)))
    return jsonify(_execute(run_id))


def _run_record(run_id: str) -> dict:
    record = _runs.get(run_id)
    if record is None or "result" not in record:
        raise Missing("找不到這次處理結果，請重新執行")
    return record


@app.get("/api/runs/<run_id>")
def get_run(run_id):
    return jsonify(_run_record(run_id)["result"])


@app.get("/api/runs/<run_id>/trace")
def row_trace(run_id):
    """某一列的處理過程。平常不會看，好奇或要覆核時才產生。"""
    record = _run_record(run_id)
    if record.get("job") is None:
        raise Missing("找不到這次的執行紀錄，請重新執行")
    row = _find_row(record["result"], request.args.get("rid", ""))
    return jsonify(trace(record["job"], record["result"], row))


@app.post("/api/runs/<run_id>/rerun")
def rerun(run_id):
    _run_record(run_id)
    return jsonify(_execute(run_id))


@app.post("/api/runs/<run_id>/reset")
def reset_review(run_id):
    """清掉這個檔案的人工決定（修改、指定的配對、確認），從頭再檢查。會先留一份可以復原。"""
    record = _run_record(run_id)
    record["review"].reset()
    log.info("重設人工決定 run=%s", run_id)
    return jsonify(_execute(run_id))


@app.post("/api/runs/<run_id>/restore")
def restore_review(run_id):
    record = _run_record(run_id)
    if not record["review"].restore():
        raise Missing("沒有可以復原的重設")
    log.info("復原重設 run=%s", run_id)
    return jsonify(_execute(run_id))


def _find_row(result: dict, rid: str) -> dict:
    for row in result["output"]["rows"]:
        if row["rid"] == rid:
            return row
    raise Missing("找不到這一列，請重新執行")


@app.post("/api/runs/<run_id>/edit")
def edit_cell(run_id):
    """修改一格。原值保留在人工修改紀錄；revert 為 true 時還原。"""
    record = _run_record(run_id)
    body = _json_body()
    rid, name = str(body.get("rid", "")), str(body.get("column", ""))
    column = next((c for c in record["result"]["output"]["columns"] if c["name"] == name), None)
    if column is None:
        raise Missing("找不到這個欄位")
    if not column["editable"]:
        raise ValueError(f"{name} 由 recipe 設定為不能修改")
    row = _find_row(record["result"], rid)
    review: ReviewStore = record["review"]
    if body.get("revert"):
        review.set_edit(rid, name, None, None)
    else:
        value = _typed(column["type"], body.get("value"))
        original = row["edited"][name] if name in row["edited"] else row["raw"].get(name, row["values"].get(name))
        review.set_edit(rid, name, original, value)
    review.save()
    log.info("人工修改 run=%s", run_id)
    return jsonify(_execute(run_id))


def _typed(kind: str, value):
    text = "" if value is None else str(value).strip()
    if len(text) > 2000:
        raise ValueError("內容太長")
    if text == "" or kind == "text":
        return text
    if kind == "date":
        parsed = parse_date(text)
        if parsed is None:
            raise ValueError("看不懂這個日期，請寫成 2026-01-31")
        return parsed.isoformat()
    parsed = parse_number(text) if kind == "number" else parse_integer(text)
    if parsed is None:
        raise ValueError("請輸入數字" if kind == "number" else "請輸入整數")
    return parsed


@app.post("/api/runs/<run_id>/match")
def decide_match(run_id):
    """指定配對：rights 是右表列代號清單；空清單代表確定沒有配對；null 代表交回自動比對。
    左表一列只能對一列的配對方式，清單最多一筆。"""
    record = _run_record(run_id)
    body = _json_body()
    match = next((m for m in record["result"]["matches"] if m["name"] == body.get("match")), None)
    if match is None:
        raise Missing("找不到這個配對")
    left, rights = str(body.get("left", "")), body.get("rights")
    if left not in match["left_rows"]:
        raise Missing("找不到左表這一列")
    if rights is not None:
        if not isinstance(rights, list) or len(rights) > 1000:
            raise ValueError("配對內容不正確")
        rights = list(dict.fromkeys(str(r) for r in rights))
        if any(r not in match["right_rows"] for r in rights):
            raise Missing("找不到右表這一列")
        if len(rights) > 1 and not match["multi"]:
            raise ValueError(f"{match['name']} 是{match['mode_label']}，左表一列只能對一列")
    review: ReviewStore = record["review"]
    review.set_match(match["name"], left, rights)
    review.save()
    log.info("指定配對 run=%s", run_id)
    return jsonify(_execute(run_id))


@app.post("/api/runs/<run_id>/dismiss")
def dismiss(run_id):
    record = _run_record(run_id)
    body = _json_body()
    keys = body.get("keys")
    if not isinstance(keys, list) or not keys or len(keys) > 5000:
        raise ValueError("請選擇要確認的警示")
    known = {i["key"] for i in record["result"]["issues"]}
    review: ReviewStore = record["review"]
    for issue_key in keys:
        if issue_key in known:
            review.set_dismissed(issue_key, bool(body.get("on", True)))
    review.save()
    return jsonify(_execute(run_id))


@app.post("/api/runs/<run_id>/mapping")
def add_mapping(run_id):
    """補上對照：之後同一份 recipe 處理其他檔案時也會用到。target 為 null 時移除。"""
    record = _run_record(run_id)
    body = _json_body()
    recipe = _read_recipe(record["recipe"])
    name = str(body.get("mapping", ""))
    spec = recipe.mappings.get(name)
    if spec is None:
        raise Missing("找不到這張對照表")
    raw = str(body.get("raw", "")).strip()
    target = body.get("target")
    if not raw or len(raw) > 200:
        raise ValueError("原始值不正確")
    store = MappingStore(paths.MAPPINGS, recipe.id)
    new_value = False
    if target is not None:
        target = str(target).strip()
        if not target or len(target) > 200 or not target.isprintable():
            raise ValueError("請選擇或輸入對應值")
        allowed = [*(spec.values or []), *store.values(name)]
        if spec.values is not None and target not in allowed:
            if not body.get("new_value"):   # 清單外的值要明確表示「新增」，避免打錯字變成新代碼
                raise ValueError(f"「{target}」不在對應值清單裡；要新增請選「新增對應值」")
            new_value = True
    store.add(name, raw, target, new_value)
    log.info("補上對照 run=%s mapping=%s", run_id, log_text(name))
    return jsonify(_execute(run_id))


@app.get("/api/runs/<run_id>/export")
def export_run(run_id):
    record = _run_record(run_id)
    result = record["result"]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stem = Path(_workbooks.get(record["workbook"], {}).get("name", "data")).stem
    name = _safe_name(f"{stem}_{result['recipe']['id']}_{stamp}.xlsx")
    path = export_excel(result, paths.OUTPUT / name)
    log.info("匯出 run=%s rows=%d", run_id, len(result["output"]["rows"]))
    return send_file(path, as_attachment=True, download_name=name)


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
                if client not in _live and now - seen > CLIENT_TIMEOUT_SECONDS:
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
