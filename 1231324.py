# pip install selenium webdriver-manager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
from datetime import datetime
import time

BASE = "https://intel.arkm.com/explorer/token/{slug}"
OUT_FILE = "top_holder_summaries.txt"

GRID_SEL = ('css selector', 'div[class*="TokenTopHolders-"][class*="topHoldersGrid"]')
ROW_SEL  = ('css selector', 'div[class*="TokenTopHolders-"][class*="topHolderRowContainer"]')
NAME_SEL = ('css selector', 'div[class*="topHolderCounterparty"]')
VAL_SEL  = ('css selector', 'span[class*="topHolderBalance"]')
PCT_SEL  = ('css selector', 'span[class*="topHolderPercent"]')
USD_SEL  = ('css selector', 'span[class*="topHolderUSD"]')

def clean(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip()

def parse_float(s: str) -> float:
    if s is None:
        return 0.0
    s = (s.replace('%', '')
           .replace('$', '')
           .replace('€', '')
           .replace('\u00A0', '')
           .replace('\u202F', '')
           .replace(',', '')
           .strip())
    if s in ('', '—', '-', 'N/A'):
        return 0.0
    # поддержка суффиксов K/M/B, если вдруг встретятся
    m = re.fullmatch(r'([-+]?\d+(?:\.\d+)?)([KMBkmb]?)', s)
    if m:
        val = float(m.group(1))
        suf = m.group(2).upper()
        if suf == 'K': val *= 1e3
        elif suf == 'M': val *= 1e6
        elif suf == 'B': val *= 1e9
        return val
    m2 = re.search(r'[-+]?\d+(?:\.\d+)?', s)
    return float(m2.group(0)) if m2 else 0.0

def make_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,900")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def fetch_sums_for_slug(driver, slug: str):
    url = BASE.format(slug=slug)
    print(f"[FETCH] {url}")
    driver.get(url)
    wait = WebDriverWait(driver, 60)

    # 1) дождаться нужной сетки
    grid = wait.until(EC.presence_of_element_located(GRID_SEL))
    # 2) дождаться появления строк именно ВНУТРИ этой сетки
    wait.until(lambda d: len(grid.find_elements(*ROW_SEL)) > 0)

    # ВАЖНО: выбираем строки ТОЛЬКО внутри grid
    rows = grid.find_elements(*ROW_SEL)
    if not rows:
        return None

    # Суммы начинаются с нуля для КАЖДОГО ключа
    sum_pct = 0.0
    sum_val = 0.0
    sum_usd = 0.0

    for r in rows:
        # имя не участвует в суммах — читаем для устойчивости селекторов
        _ = clean(r.find_element(*NAME_SEL).text)
        val = clean(r.find_element(*VAL_SEL).text)
        pct = clean(r.find_element(*PCT_SEL).text)
        usd = clean(r.find_element(*USD_SEL).text)

        sum_pct += parse_float(pct)
        sum_val += parse_float(val)
        sum_usd += parse_float(usd)

    return {"slug": slug, "sum_pct": sum_pct, "sum_val": sum_val, "sum_usd": sum_usd}

def format_block(res):
    return (
        f"KEY: {res['slug']}\n"
        f"====== СУММЫ ======\n"
        f"∑ процентов:           {res['sum_pct']:.6f}\n"
        f"∑ Balance:    {res['sum_val']:.6f}\n"
        f"∑ USD:        {res['sum_usd']:.6f}\n"
    )

def main(slugs):
    driver = make_driver()
    blocks = []
    try:
        for slug in slugs:
            time.sleep(30)  # небольшая пауза между запросами
            try:
                res = fetch_sums_for_slug(driver, slug)
                if not res:
                    print(f"[WARN] Нет данных для: {slug}")
                    continue
                block = format_block(res)
                print(block, end="")
                blocks.append(block)
            except Exception as e:
                print(f"[ERROR] {slug}: {e}")
    finally:
        driver.quit()

    if blocks:
        header = f"# Сводка сумм (сформировано {datetime.utcnow().isoformat(timespec='seconds')}Z)\n\n"
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(header + "\n\n".join(blocks) + "\n")
        print(f"\n[OK] Записано в файл: {OUT_FILE}")
    else:
        print("[WARN] Пусто — ничего не записано.")

if __name__ == "__main__":
    SLUGS = [
        "helium",
        "immutable-x.json",
        "starknet"
    ]
    print(f"[INFO] Сформировано {len(SLUGS)} URL:")
    for s in SLUGS:
        print(f"  • {BASE.format(slug=s)}")
    main(SLUGS)



    SLUGS_1 = [
        "arbitrum",
        "optimism",
        "internet-computer",
        "pyth-network",
        "near",
        "immutable-x.json",
        "helium",
        "usual",
        "the-open-network",
        "worldcoin-wld",
        "omnibridge-bridged-zcash-solana",
        "oobit",
        "ethereum"
    ]

    TokenTopHolders - module__0lehJa__topHoldersGrid