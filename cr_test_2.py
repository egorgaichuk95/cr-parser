# top_holders_parser_filespec.py
from bs4 import BeautifulSoup
import re
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
import os

OUT_FILE = "top_holder_summaries.txt"

# ---------- utils ----------

def _norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00A0", " ").replace("\u202F", " ").strip())

def _to_float(num_str: Optional[str]) -> float:
    """
    Robust number parser:
      '7,853,385.27' -> 7853385.27
      '4.22%'        -> 4.22
      '$13.9M'       -> 13900000.0
      '—' / '-'      -> 0.0
    """
    if num_str is None:
        return 0.0
    s = _norm_space(num_str).replace(",", "")
    if s in ("", "—", "-", "N/A"):
        return 0.0

    # percentages: keep as number (not fraction)
    if s.endswith("%"):
        try:
            return float(s[:-1])
        except ValueError:
            return 0.0

    # leading currency
    if s and s[0] in "$€":
        s = s[1:]

    # suffixes
    mult = 1.0
    if s and s[-1] in "KkMmBb":
        mult = {"K": 1e3, "M": 1e6, "B": 1e9}[s[-1].upper()]
        s = s[:-1]

    try:
        return float(s) * mult
    except ValueError:
        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        return float(m.group(0)) * mult if m else 0.0

# ---------- core parsing ----------

def _row_matcher(c: Optional[List[str]]) -> bool:
    return bool(c) and "__topHolderRowContainer" in " ".join(c)

def _bal_matcher(c: Optional[List[str]]) -> bool:
    return bool(c) and "__topHolderBalance" in " ".join(c)

def _pct_matcher(c: Optional[List[str]]) -> bool:
    return bool(c) and "__topHolderPercent" in " ".join(c)

def _usd_matcher(c: Optional[List[str]]) -> bool:
    return bool(c) and "__topHolderUSD" in " ".join(c)

def _grid_matcher(c: Optional[List[str]]) -> bool:
    cs = " ".join(c or [])
    return "TokenTopHolders-" in cs and "topHoldersGrid" in cs

def parse_top_holders_html(html: str) -> List[dict]:
    """
    Returns list of rows with normalized and raw values.
    Each dict contains: name, balance_raw, percent_raw, usd_raw, balance, percent, usd
    """
    soup = BeautifulSoup(html, "html.parser")

    scope = soup.find("div", class_=_grid_matcher) or soup

    out: List[dict] = []
    for row in scope.find_all("div", class_=_row_matcher):
        counterparty_div = row.find("div", class_=lambda c: c and "__topHolderCounterparty" in " ".join(c))
        name = _norm_space(counterparty_div.get_text(separator=" ", strip=True) if counterparty_div else "")

        bal_el = row.find("span", class_=_bal_matcher)
        pct_el = row.find("span", class_=_pct_matcher)
        usd_el = row.find("span", class_=_usd_matcher)

        bal_raw = bal_el.get_text(strip=True) if bal_el else None
        pct_raw = pct_el.get_text(strip=True) if pct_el else None
        usd_raw = usd_el.get_text(strip=True) if usd_el else None

        out.append({
            "name": name,
            "balance_raw": bal_raw,
            "percent_raw": pct_raw,
            "usd_raw": usd_raw,
            "balance": _to_float(bal_raw),
            "percent": _to_float(pct_raw),
            "usd": _to_float(usd_raw),
        })

    return out

def sum_rows(rows: List[dict]) -> dict:
    sum_balance = sum(r.get("balance", 0.0) for r in rows)
    sum_percent = sum(r.get("percent", 0.0) for r in rows)
    sum_usd     = sum(r.get("usd", 0.0) for r in rows)
    return {
        "sum_balance": float(sum_balance),
        "sum_percent": float(sum_percent),
        "sum_usd": float(sum_usd),
        "row_count": len(rows),
    }

# ---------- high-level API (filespec: {filename: html_code}) ----------

def parse_filespec(filespec: Dict[str, str]) -> Dict[str, List[dict]]:
    """
    Input:  { "helium.html": "<div ...>", "immutable-x.json.html": "<div ...>", ... }
    Output: { "helium.html": [rows...],  "immutable-x.json.html": [rows...], ... }
    Also writes each HTML to a file in the same directory as this module.
    """
    base_dir = Path(__file__).parent.resolve()
    result: Dict[str, List[dict]] = {}

    for fname, html in filespec.items():
        # sanitize file name to avoid path traversal
        fname_safe = os.path.basename(fname)
        file_path = base_dir / fname_safe

        # write file next to this module
        file_path.write_text(html, encoding="utf-8")

        # parse the provided HTML content
        result[fname_safe] = parse_top_holders_html(html)

    return result

def compute_summaries_from_filespec(filespec: Dict[str, str]) -> Dict[str, dict]:
    """
    For each filename -> HTML, compute sums over all top-holder rows.
    Returns: { filename: {"sum_balance":..., "sum_percent":..., "sum_usd":..., "row_count": N}, ... }
    """
    summaries: Dict[str, dict] = {}
    parsed = parse_filespec(filespec)
    for fname, rows in parsed.items():
        summaries[fname] = sum_rows(rows)
    return summaries

# ---------- formatting & saving ----------

def _format_block(key: str, sums: dict) -> str:
    return (
        f"KEY: {key}\n"
        f"====== СУММЫ ======\n"
        f"∑ процентов: {sums['sum_percent']:.6f}\n"
        f"∑ Balance:   {sums['sum_balance']:.6f}\n"
        f"∑ USD:       {sums['sum_usd']:.6f}\n"
        f"(rows: {sums.get('row_count', 0)})\n"
    )

def compute_and_save_from_filespec(filespec: Dict[str, str], out_file: str = OUT_FILE) -> None:
    summaries = compute_summaries_from_filespec(filespec)
    blocks = [_format_block(key, sums) for key, sums in summaries.items()]
    header = f"# Сводка сумм (сформировано {datetime.utcnow().isoformat(timespec='seconds')}Z)\n\n"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(header + "\n\n".join(blocks) + "\n")
    print(f"[OK] Записано в файл: {out_file}")

# ---------- CLI example ----------

if __name__ == "__main__":
    filespec = {
        # "helium.html": r"""<div class="TokenTopHolders-module__...__topHolderRowContainer ..."> ... </div>""",
        # "immutable-x.json.html": r"""...""",
        # "starknet.html": r"""...""",
    }

    if not filespec:
        print("[INFO] No input provided. Import and call compute_and_save_from_filespec(filespec).")
    else:
        compute_and_save_from_filespec(filespec)
