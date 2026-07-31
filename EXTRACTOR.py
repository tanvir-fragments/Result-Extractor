"""
Scrapes HSC results from x
for a list of student IDs, using a chosen Level + Exam.

STATUS: form-filling is wired up. The RESULT EXTRACTION part (bottom of
scrape_one) still has placeholder selectors marked # CHANGE ME -- fill
these in once you've inspected what a successful search result looks like.
"""

import csv
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

URL = "x"

# ---- CONFIG: change these as needed ----
LEVEL = "HSC 1st Year"              # or "HSC 2nd Year"
EXAM = "Annual Examination"         # or "Half Yearly Examination", etc.
STUDENT_IDS = [str(i) for i in range(20251001, 20251301)]  # CHANGE ME: your real IDs
OUTPUT_CSV = "results.csv"
DELAY_BETWEEN_REQUESTS = 1.5        # seconds -- be polite, avoid getting blocked
# -----------------------------------------


def make_driver(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    # Selenium 4.6+ auto-downloads a matching chromedriver -- no manual install needed
    return webdriver.Chrome(options=opts)


def select_by_label(driver, label_text, option_text):
    """Find a <select> that sits in the same form-group as a given label,
    and choose the option matching option_text."""
    select_el = driver.find_element(
        By.XPATH,
        f"//label[contains(text(), '{label_text}')]/ancestor::div[contains(@class,'form-group')]//select"
    )
    Select(select_el).select_by_visible_text(option_text)


def scrape_one(driver, student_id):
    driver.get(URL)

    # Fill dropdowns FIRST -- selecting Exam can trigger an AJAX update
    # (it populates the Class Test dropdown), which may reset other fields.
    select_by_label(driver, "Level", LEVEL)
    select_by_label(driver, "Exam", EXAM)

    # Small pause to let any AJAX triggered by the dropdowns settle
    time.sleep(0.5)

    # Fill Student ID LAST so it isn't wiped out by the above
    id_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.NAME, "student_id"))
    )
    id_input.clear()
    id_input.send_keys(student_id)

    # Click Search
    search_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Search')]")
    search_btn.click()

    # ---- RESULT EXTRACTION ----
    start_wait = time.time()
    try:
        # Wait for the info table (Exam/Name/Father/... rows) to appear
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//td[normalize-space(.)='Name']"))
        )
        elapsed = time.time() - start_wait
        print(f"  (result loaded in {elapsed:.1f}s)")
        # Scroll to bottom in case the marks table further down needs to
        # come into view to fully render
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
    except TimeoutException:
        # Most likely: no result exists for this ID / level / exam combo.
        # But could also mean something didn't fill in/submit correctly --
        # save a screenshot so we can check.
        debug_path = f"debug_{student_id}.png"
        try:
            # Resize window to fit the full page height so the screenshot
            # captures everything, not just the visible viewport
            total_height = driver.execute_script("return document.body.scrollHeight")
            driver.set_window_size(1200, total_height + 100)
            driver.save_screenshot(debug_path)
        except Exception:
            pass
        print(f"  - No result found for {student_id} (screenshot: {debug_path})")
        return {"student_id": student_id, "name": None, "cgpa": None}

    try:
        name = driver.find_element(
            By.XPATH, "//td[normalize-space(.)='Name']/following-sibling::td[1]"
        ).text.strip()

        # CGPA lives in the subjects table, in the column headed "CGPA".
        # It's usually only filled in on the first subject row (merged cell).
        headers = driver.find_elements(
            By.XPATH, "//table[.//th[normalize-space(text())='CGPA']]//th"
        )
        header_texts = [h.text.strip() for h in headers]
        cgpa_index = header_texts.index("CGPA")

        rows = driver.find_elements(
            By.XPATH, "//table[.//th[normalize-space(text())='CGPA']]/tbody/tr"
        )
        cgpa = None
        for row in rows:
            tds = row.find_elements(By.TAG_NAME, "td")
            if len(tds) > cgpa_index and tds[cgpa_index].text.strip():
                cgpa = tds[cgpa_index].text.strip()
                break

        return {"student_id": student_id, "name": name, "cgpa": cgpa}
    except Exception as e:
        print(f"  ! Unexpected error parsing result for {student_id}: {type(e).__name__}: {e}")
        return {"student_id": student_id, "name": None, "cgpa": None}
    # ----------------------------------------


def main():
    driver = make_driver(headless=True)  # set False first to watch it work
    results = []

    try:
        for i, sid in enumerate(STUDENT_IDS, start=1):
            print(f"[{i}/{len(STUDENT_IDS)}] Fetching {sid}...")
            try:
                row = scrape_one(driver, sid)
            except Exception as e:
                # Genuine crash (browser died, page structure changed, etc.)
                print(f"  ! Driver error on {sid}: {type(e).__name__}: {e}")
                print("  Restarting browser and retrying...")
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = make_driver(headless=True)
                try:
                    row = scrape_one(driver, sid)
                except Exception as e2:
                    print(f"  ! Retry also failed for {sid}: {type(e2).__name__}: {e2}")
                    row = {"student_id": sid, "name": None, "cgpa": None}
            results.append(row)
            time.sleep(DELAY_BETWEEN_REQUESTS)
    finally:
        driver.quit()

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["student_id", "name", "cgpa"])
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDone. Saved {len(results)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
