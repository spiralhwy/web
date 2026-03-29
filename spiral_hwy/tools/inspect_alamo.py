#!/usr/bin/env python3
"""
One-time DOM inspector for the Alamo Drafthouse SF page.
Run this to capture the rendered HTML after Angular initializes,
so you can identify the exact selectors needed for the scraper.

Usage:
    cd spiral_hwy/tools
    python inspect_alamo.py
"""

import time
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from web_scraper import get_driver

URL = "https://drafthouse.com/sf"
OUTPUT_FILE = Path(__file__).parent.parent / "alamo_dom_dump.html"
WAIT_FOR_CLASS = "adc-show-card"
TIMEOUT = 30


def main():
    driver = get_driver()
    try:
        print(f"Loading {URL} ...")
        driver.get(URL)

        print(f"Waiting up to {TIMEOUT}s for '{WAIT_FOR_CLASS}' elements ...")
        WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, WAIT_FOR_CLASS))
        )
        # Let the page settle a bit more
        time.sleep(2)

        cards = driver.find_elements(By.CLASS_NAME, WAIT_FOR_CLASS)
        print(f"Found {len(cards)} '{WAIT_FOR_CLASS}' elements.")

        # Print a summary of the first card's inner HTML
        if cards:
            print("\n--- First card HTML ---")
            print(cards[0].get_attribute("outerHTML")[:3000])
            print("--- End of first card ---\n")

        # Save full page HTML
        html = driver.page_source
        OUTPUT_FILE.write_text(html, encoding="utf-8")
        print(f"Full page HTML saved to: {OUTPUT_FILE}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
