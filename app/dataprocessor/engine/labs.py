"""實地練習（labs）的載入、片段插入、行號換算與結果驗證。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def load_labs(demo_dir: Path) -> dict[str, dict[str, Any]]:
    data = json.loads((demo_dir / "labs.json").read_text(encoding="utf-8"))
    return {item["id"]: item for item in data.get("labs", [])}


def list_labs(demo_dir: Path) -> list[dict[str, Any]]:
    """只回傳公開資訊（id、標題、步驟數），不含預期值與解答。"""
    data = json.loads((demo_dir / "labs.json").read_text(encoding="utf-8"))
    return [{"id": item["id"], "title": item["title"], "steps": 4} for item in data.get("labs", [])]


def insert_snippet(template: str, marker: str, snippet: str) -> tuple[str, int, int]:
    """依 marker 所在行的縮排，逐行縮排 snippet 後取代。回傳 (完整文字, marker 所在 1-based 行號, 片段行數)。"""
    lines = template.splitlines()
    slot_idx = next((i for i, line in enumerate(lines) if marker in line), None)
    if slot_idx is None:
        raise ValueError("練習範本缺少插入標記")
    indent = lines[slot_idx][: len(lines[slot_idx]) - len(lines[slot_idx].lstrip(" "))]
    raw_lines = snippet.replace("\r\n", "\n").split("\n") if snippet.strip() else []
    indented = [f"{indent}{line}" if line.strip() else "" for line in raw_lines]
    merged = lines[:slot_idx] + indented + lines[slot_idx + 1 :]
    return "\n".join(merged) + "\n", slot_idx + 1, len(raw_lines)


_LINE_RE = re.compile(r"第\s*(\d+)\s*行")


def remap_problem_lines(problems: list[str], slot_line: int, snippet_lines: int) -> list[str]:
    """把 YAML 錯誤訊息裡的整份檔案行號，換算成片段裡的行號。"""
    end_line = slot_line + max(1, snippet_lines)
    remapped = []
    for text in problems:
        def _sub(match: re.Match) -> str:
            n = int(match.group(1))
            if slot_line <= n <= end_line:
                return f"片段第 {n - slot_line + 1} 行"
            return match.group(0)
        remapped.append(_LINE_RE.sub(_sub, text))
    return remapped


def sample_preview(sheets) -> str:
    """整理範例資料前 3 列，給「複製給 AI 的提問」附在提問裡。"""
    parts = []
    for sheet in sheets[:2]:
        rows = [r for r in sheet.rows if any(v is not None and str(v).strip() != "" for v in r)]
        if not rows:
            continue
        lines = [f"工作表「{sheet.name}」："]
        for row in rows[:4]:
            lines.append(" | ".join("" if v is None else str(v).replace("\n", "\\n") for v in row))
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _find_output_row(result: dict, title: str) -> dict | None:
    cols = result.get("output", {}).get("columns", [])
    first = cols[0]["name"] if cols else None
    for row in result.get("output", {}).get("rows", []):
        if first and str(row["values"].get(first, "")) == title:
            return row
        if any(str(v) == title for v in row["values"].values()):
            return row
    return None


def _row_title(record: dict, title_cols: list[str]) -> str:
    vals = record.get("values", {})
    return "・".join(str(vals[c]) for c in title_cols if vals.get(c) not in (None, ""))


def evaluate_checks(result: dict, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for ck in checks:
        kind = ck["type"]
        how = ck.get("how", "")
        if kind == "match":
            m = next((x for x in result.get("matches", []) if x["name"] == ck["match"]), None)
            expected = ck["right"]
            actual = "（沒有）"
            passed = False
            left_label = m["left_label"] if m else "資料"
            if m:
                for row in m["rows"]:
                    if _row_title(m["left_rows"][row["left"]], m["left_title"]) == ck["left"]:
                        rights = [_row_title(m["right_rows"][r], m["right_title"]) for r in row["rights"] if r in m["right_rows"]]
                        actual = "、".join(rights) if rights else "（沒有）"
                        passed = (expected == "none" and not rights) or (expected in rights)
                        break
            label = f"{left_label} {ck['left']} 配到 {expected}"
            hint = "" if passed else f"{left_label} {ck['left']}：配到{actual}，應該是 {expected}。{how}"
            out.append({"label": label, "pass": passed, "expected": expected, "actual": actual, "hint": hint})

        elif kind == "excluded":
            expected = list(ck["expected"])
            actual = []
            for entry in result.get("excluded", []):
                vals = entry.get("values", {})
                first_val = next((str(v) for v in vals.values() if v not in (None, "")), "")
                actual.append(first_val)
            passed = sorted(actual) == sorted(expected)
            actual_text = "、".join(actual) if actual else "（沒有）"
            exp_text = "、".join(expected) if expected else "（沒有）"
            label = f"排除清單為 {exp_text}"
            hint = "" if passed else f"排除清單：目前是 {actual_text}，應該是 {exp_text}。{how}"
            out.append({"label": label, "pass": passed, "expected": expected, "actual": actual, "hint": hint})

        elif kind == "field":
            row = _find_output_row(result, ck["row"])
            col = ck["column"]
            expected = ck["expected"]
            actual = row["values"].get(col) if row else None
            passed = str(actual) == str(expected)
            actual_text = "（空白）" if actual in (None, "") else str(actual).replace("\n", " ↵ ")
            label = f"{ck['row']} 的「{col}」為 {expected}"
            hint = "" if passed else f"{ck['row']} 的「{col}」：抓到 {actual_text}，應該是 {expected}。{how}"
            out.append({"label": label, "pass": passed, "expected": expected, "actual": actual, "hint": hint})

        elif kind == "issue":
            row = _find_output_row(result, ck["row"])
            issues = [result["issues"][i] for i in (row["issues"] if row else [])]
            if ck.get("code"):
                issues = [i for i in issues if i.get("code") == ck["code"]]
            if ck.get("stage"):
                issues = [i for i in issues if i.get("stage") == ck["stage"]]
            issues = [i for i in issues if not i.get("dismissed") and i.get("level") != "skip"]
            want_present = bool(ck.get("present", True))
            has_issue = len(issues) > 0
            hl_ok = True
            if want_present and has_issue and ck.get("highlight"):
                want_hl = set(ck["highlight"])
                hl_ok = any(want_hl.issubset(set(i.get("out_columns") or [])) for i in issues)
            passed = (has_issue == want_present) and hl_ok
            if want_present:
                label = f"{ck['row']} 有對應警示"
                actual_text = "沒有警示" if not has_issue else "缺少標示欄位"
                exp_text = "有驗證警示" + (f"（含 {', '.join(ck['highlight'])}）" if ck.get("highlight") else "")
            else:
                label = f"{ck['row']} 沒有多餘警示"
                actual_text = f"有 {len(issues)} 則警示"
                exp_text = "沒有警示"
            hint = "" if passed else f"{ck['row']}：目前{actual_text}，應該是{exp_text}。{how}"
            out.append({"label": label, "pass": passed, "expected": exp_text, "actual": actual_text, "hint": hint})

        elif kind == "count":
            expected = int(ck["expected"])
            actual = int(result.get("counts", {}).get("review", 0))
            passed = actual == expected
            label = f"需檢查列數為 {expected}"
            hint = "" if passed else f"需檢查列數：目前是 {actual}，應該是 {expected}。{how}"
            out.append({"label": label, "pass": passed, "expected": expected, "actual": actual, "hint": hint})
    return out
