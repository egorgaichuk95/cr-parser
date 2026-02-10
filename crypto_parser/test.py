from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterable
import json
import re
from decimal import Decimal, ROUND_HALF_UP

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from crypto_parser.keys_for_parse import ONLY_KEYS

# ---------- Config ----------
RESOURCES_DIR = Path(__file__).parent / "html_resources"
OUT_XLSX = Path(__file__).parent / "top_holder_summaries.xlsx"

# ширины «в 3 раза меньше» относительно версии ×5
WIDTH_SCALE = 5 / 3        # ≈1.6667 от базовых
FONT_SCALE = 4             # крупнее шрифт и строки ×4
BASE_ROW_HEIGHT_PT = 15


# ---------- IO helpers ----------
def _normalize_keys(keys: Optional[Iterable[str]]) -> Optional[set[str]]:
    if not keys:
        return None
    norm = set()
    for k in keys:
        if not k:
            continue
        k = k.strip().lower()
        if not k:
            continue
        norm.add(k)
        if k.endswith(".json"):
            norm.add(Path(k).stem)
        else:
            norm.add(k + ".json")
    return norm


def collect_json_filespec(
    resources_dir: str | Path | None = None,
    only_keys: Optional[List[str]] = None,
) -> Dict[str, dict]:
    if resources_dir is None:
        resources_dir = RESOURCES_DIR
    resources_dir = Path(resources_dir)
    if not resources_dir.exists():
        raise FileNotFoundError(f"Directory not found: {resources_dir}")

    allowed = _normalize_keys(only_keys)
    filespec: Dict[str, dict] = {}
    found_names_lower: set[str] = set()

    for p in sorted(resources_dir.glob("*.json")):
        fname = p.name
        stem = p.stem
        fname_l = fname.lower()
        stem_l = stem.lower()

        if allowed is not None and (fname_l not in allowed and stem_l not in allowed):
            continue

        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            payload = json.loads(p.read_text(encoding="utf-8", errors="replace"))

        filespec[fname] = payload
        found_names_lower.update({fname_l, stem_l})

    if allowed is not None:
        missing = {k for k in allowed if k not in found_names_lower}
        missing_clean = {Path(m).stem for m in missing}
        if missing_clean:
            print("[WARN] Не найдены файлы для ключей:", ", ".join(sorted(missing_clean)))

    return filespec


# ---------- Parsing utilities ----------
_WS = re.compile(r"\s+")


def _to_float(num_str: Optional[str]) -> float:
    if not num_str:
        return 0.0

    s = str(num_str).strip().replace("\u00A0", "").replace("\u202F", "")
    s = s.replace(",", "")

    if s.endswith("%"):
        try:
            return float(s[:-1])
        except ValueError:
            return 0.0

    if s.startswith(("$", "€")):
        s = s[1:]

    mult = 1.0
    if s.endswith(("K", "M", "B", "k", "m", "b")):
        suf = s[-1].upper()
        s = s[:-1]
        mult = {"K": 1e3, "M": 1e6, "B": 1e9}[suf]

    try:
        return float(s) * mult
    except ValueError:
        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        return float(m.group(0)) * mult if m else 0.0


# ---------- Summarization ----------
def summarize_rows(rows: List[dict]) -> Tuple[float, float, float]:
    sum_pct = 0.0
    sum_bal = 0.0
    sum_usd = 0.0
    for r in rows or []:
        sum_pct += _to_float(r.get("percent_raw"))
        sum_bal += _to_float(r.get("balance_raw"))
        sum_usd += _to_float(r.get("usd_raw"))
    return (sum_pct, sum_bal, sum_usd)


# ---------- Formatting (stdout) ----------
def format_block(key: str, payload: dict, sums: Tuple[float, float, float]) -> str:
    sum_pct, sum_bal, sum_usd = sums
    source = payload.get("source") or ""
    collected_at = payload.get("collected_at") or ""
    meta = []
    if source:
        meta.append(f"source: {source}")
    if collected_at:
        meta.append(f"collected_at: {collected_at}")
    meta_line = (" (" + "; ".join(meta) + ")") if meta else ""
    return (
        f"KEY: {key}{meta_line}\n"
        f"====== SUMS ======\n"
        f"∑ Percent:     {sum_pct:.6f}\n"
        f"∑ Balance:     {sum_bal:.6f}\n"
        f"∑ USD:         {sum_usd:.6f}\n"
    )


# ---------- Humanize ----------
def _humanize(n: Decimal, decimals: int) -> str:
    """
    Возвращает строку с узкими пробелами как разделителями тысяч и запятой как
    десятичным разделителем. Пример: 276 356 832 770,00
    """
    s = f"{n:,.{decimals}f}"           # 276,356,832,770.00 (EN)
    s = s.replace(",", " ")            # 276 356 832 770.00
    s = s.replace(" ", "\u202F")       # 276 356 832 770.00 (узкий пробел)
    s = s.replace(".", ",")            # 276 356 832 770,00
    return s


# ---------- Orchestration ----------
def run(only_keys: Optional[List[str]] = None) -> None:
    filespec = collect_json_filespec(only_keys=only_keys)
    if not filespec:
        if only_keys:
            print("[WARN] По фильтру ключей не найдено ни одного JSON-файла.")
        else:
            print("[WARN] Нет JSON-файлов в html_resources.")
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Sums"

    # крупный вид
    ws.sheet_view.zoomScale = 400
    ws.sheet_view.zoomScaleNormal = 400

    # ширины (A — уменьшена в 1.5 раза; B–E — ×2)
    base = {"A": 8, "B": 42, "C": 18, "D": 20, "E": 20}
    ws.column_dimensions["A"].width = min((base["A"] * WIDTH_SCALE) / 1.5, 255)
    ws.column_dimensions["B"].width = min(base["B"] * WIDTH_SCALE * 1, 255)
    ws.column_dimensions["C"].width = min(base["C"] * WIDTH_SCALE * 2, 255)
    ws.column_dimensions["D"].width = min(base["D"] * WIDTH_SCALE * 2, 255)
    ws.column_dimensions["E"].width = min(base["E"] * WIDTH_SCALE * 2, 255)

    # высота строк ×4
    ws.sheet_format.defaultRowHeight = BASE_ROW_HEIGHT_PT * FONT_SCALE

    # шапка
    headers = ["#", "KEY", "∑ Percent", "∑ Balance", "∑ USD"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, size=11 * FONT_SCALE)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:E{ws.max_row}"

    # данные + нумерация
    idx = 1
    max_key_len = len("KEY")
    for filename in sorted(filespec.keys()):
        payload = filespec[filename]
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            print(f"[WARN] Неверный формат 'rows' в: {filename}")
            continue

        sum_pct, sum_bal, sum_usd = summarize_rows(rows)

        # аккуратные числа (Decimal -> строки)
        pct = Decimal(str(sum_pct)).quantize(Decimal("0.000000"), rounding=ROUND_HALF_UP)
        bal = Decimal(str(sum_bal)).quantize(Decimal("0.00"),      rounding=ROUND_HALF_UP)
        usd = Decimal(str(sum_usd)).quantize(Decimal("0.00"),      rounding=ROUND_HALF_UP)

        pct_s = _humanize(pct, 6)
        bal_s = _humanize(bal, 2)
        usd_s = _humanize(usd, 2)

        ws.append([idx, filename, pct_s, bal_s, usd_s])
        r = ws.max_row

        # стиль строки
        for col in ("A", "B", "C", "D", "E"):
            c = ws[f"{col}{r}"]
            c.font = Font(size=11 * FONT_SCALE)
            c.alignment = Alignment(vertical="center")

        # текстовый формат и выравнивание вправо для числовых колонок
        for col in ("C", "D", "E"):
            c = ws[f"{col}{r}"]
            c.number_format = "@"
            c.alignment = Alignment(horizontal="right", vertical="center")
            need = len(str(c.value)) + 2
            ws.column_dimensions[col].width = max(ws.column_dimensions[col].width or 10, need)

        # подгон ширины под KEY
        max_key_len = max(max_key_len, len(filename) + 2)
        ws.column_dimensions["B"].width = max(ws.column_dimensions["B"].width or 10, max_key_len)

        # stdout как раньше
        block = format_block(filename, payload, (sum_pct, sum_bal, sum_usd))
        print(block, end="")

        idx += 1

    ws.auto_filter.ref = f"A1:E{ws.max_row}"

    wb.save(OUT_XLSX)
    print(f"\n[OK] Записано в: {OUT_XLSX}")


if __name__ == "__main__":
    print(f"[INFO] Сканируем: {RESOURCES_DIR}")
    use_filter = len(ONLY_KEYS) > 0
    run(ONLY_KEYS if use_filter else None)
