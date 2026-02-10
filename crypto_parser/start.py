# start.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Iterable
import json
import re

from app.tools.crypto_parser.keys_for_parse import ONLY_KEYS

# ---------- Config ----------
RESOURCES_DIR = Path(__file__).parent / "html_resources"  # папка с *.json
OUT_FILE = Path(__file__).parent / "top_holder_summaries.txt"

# ---------- IO helpers ----------
def _normalize_keys(keys: Optional[Iterable[str]]) -> Optional[set[str]]:
    """
    Нормализуем список ключей: к нижнему регистру, убираем пробелы.
    Поддерживаем варианты с/без .json.
    Возвращаем множество stem/filename без учёта регистра.
    """
    if not keys:
        return None
    norm = set()
    for k in keys:
        if not k:
            continue
        k = k.strip().lower()
        if not k:
            continue
        norm.add(k)  # как есть (на случай 'helium.json')
        if k.endswith(".json"):
            norm.add(Path(k).stem)  # 'helium'
        else:
            norm.add(k + ".json")   # 'helium.json'
    return norm

def collect_json_filespec(
    resources_dir: str | Path | None = None,
    only_keys: Optional[List[str]] = None,
) -> Dict[str, dict]:
    """
    Сканируем папку и возвращаем:
      {
        "helium.json": { "source": "...", "collected_at": "...", "rows": [...] },
        ...
      }

    Если передан only_keys = ['helium', 'starknet', ...],
    обрабатываем ТОЛЬКО файлы, имена которых совпадают с ключами (с/без .json, регистр не важен).
    """
    if resources_dir is None:
        resources_dir = RESOURCES_DIR

    resources_dir = Path(resources_dir)
    if not resources_dir.exists():
        raise FileNotFoundError(f"Directory not found: {resources_dir}")

    allowed = _normalize_keys(only_keys)  # None -> брать всё
    filespec: Dict[str, dict] = {}
    found_names_lower: set[str] = set()

    for p in sorted(resources_dir.glob("*.json")):
        fname = p.name
        stem = p.stem
        fname_l = fname.lower()
        stem_l = stem.lower()

        if allowed is not None and (fname_l not in allowed and stem_l not in allowed):
            # фильтр включён — пропускаем неразрешённые файлы
            continue

        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            payload = json.loads(p.read_text(encoding="utf-8", errors="replace"))

        filespec[fname] = payload
        found_names_lower.update({fname_l, stem_l})

    # Диагностика: какие ключи из фильтра не найдены
    if allowed is not None:
        missing = {k for k in allowed if k not in found_names_lower}
        # отсекаем дубликаты вида 'helium'/'helium.json'
        missing_clean = {Path(m).stem for m in missing}
        if missing_clean:
            print("[WARN] Не найдены файлы для ключей:",
                  ", ".join(sorted(missing_clean)))

    return filespec

# ---------- Parsing utilities ----------
_WS = re.compile(r"\s+")

def _norm_space(text: Optional[str]) -> str:
    return _WS.sub(" ", (text or "").strip())

def _to_float(num_str: Optional[str]) -> float:
    """
    Нормализация чисел:
      '7,853,385.27'  -> 7853385.27
      '4.22%'         -> 4.22
      '$13.9M'        -> 13900000.0
      '$1,234'        -> 1234.0
    Пустые/некорректные -> 0.0
    """
    if not num_str:
        return 0.0

    s = str(num_str).strip().replace("\u00A0", "").replace("\u202F", "")
    s = s.replace(",", "")

    # проценты
    if s.endswith("%"):
        try:
            return float(s[:-1])
        except ValueError:
            return 0.0

    # убрать валютные символы
    if s.startswith(("$", "€")):
        s = s[1:]

    # суффиксы K/M/B
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
    """
    Ожидается список словарей вида:
      { "name": "...", "balance_raw": "...", "percent_raw": "...", "usd_raw": "..." }
    Возвращает (sum_percent, sum_balance, sum_usd).
    """
    sum_pct = 0.0
    sum_bal = 0.0
    sum_usd = 0.0

    for r in rows or []:
        sum_pct += _to_float(r.get("percent_raw"))
        sum_bal += _to_float(r.get("balance_raw"))
        sum_usd += _to_float(r.get("usd_raw"))

    return (sum_pct, sum_bal, sum_usd)

# ---------- Formatting ----------
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

# ---------- Orchestration ----------
def run(only_keys: Optional[List[str]] = None) -> None:
    """
    only_keys — фильтр по ключам/именам файлов (например, ['helium', 'starknet']).
    Если None — обрабатываются все *.json.
    """
    filespec = collect_json_filespec(only_keys=only_keys)
    if not filespec:
        if only_keys:
            print("[WARN] По фильтру ключей не найдено ни одного JSON-файла.")
        else:
            print("[WARN] Нет JSON-файлов в html_resources.")
        return

    blocks: List[str] = []
    for filename in sorted(filespec.keys()):
        payload = filespec[filename]
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            print(f"[WARN] Неверный формат 'rows' в: {filename}")
            continue

        sums = summarize_rows(rows)
        block = format_block(filename, payload, sums)
        print(block, end="")
        blocks.append(block)

    if blocks:
        header = f"# Sums summary (generated {datetime.utcnow().isoformat(timespec='seconds')}Z)\n\n"
        OUT_FILE.write_text(header + "\n\n".join(blocks) + "\n", encoding="utf-8")
        print(f"\n[OK] Записано в: {OUT_FILE}")
    else:
        print("[WARN] Пусто — нечего записывать.")

if __name__ == "__main__":
    print(f"[INFO] Сканируем: {RESOURCES_DIR}")
    use_filter = len(ONLY_KEYS) > 0
    run(ONLY_KEYS if use_filter else None)

