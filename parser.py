# parser.py
import json
import re
from pathlib import Path
from typing import List, Dict, Any

_WS = re.compile(r"\s+")

def _to_float(num_str: Any) -> float:
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

def process_directory(data_dir: Path) -> List[Dict[str, float]]:
    results = []
    
    if not data_dir.exists():
        return results

    for p in data_dir.glob("*.json"):
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            try:
                payload = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
        except json.JSONDecodeError:
            continue
            
        source_url = payload.get("source", "")
        # Extract token name from url like https://intel.arkm.com/explorer/token/aevo-exchange
        token_name = "Unknown"
        if source_url:
            parts = source_url.rstrip("/").split("/")
            if parts:
                token_name = parts[-1]
        
        # fallback to filename if needed
        if token_name == "Unknown":
            token_name = p.stem
            
        rows = payload.get("rows", [])
        if not isinstance(rows, list):
            continue
            
        sum_pct = 0.0
        sum_bal = 0.0
        sum_usd = 0.0

        for r in rows:
            sum_pct += _to_float(r.get("percent_raw"))
            sum_bal += _to_float(r.get("balance_raw"))
            sum_usd += _to_float(r.get("usd_raw"))
            
        results.append({
            "Token": token_name,
            "Sum Percent": sum_pct,
            "Sum Balance": sum_bal,
            "Sum USD": sum_usd
        })
        
    return results
