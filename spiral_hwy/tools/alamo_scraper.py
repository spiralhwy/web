#!/usr/bin/env python3
"""
Scraper for Alamo Drafthouse SF now-playing listings.

Architecture:
1. Load https://drafthouse.com/sf and find the #now-playing section.
2. Extract currently-playing show slugs from cards without an open-date badge.
3. Visit each /sf/show/{slug} page, select SF location, iterate date tabs,
   collect showtimes, and build MovieShowing/MovieListing objects.
"""

import base64
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytz
import requests
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from web_scraper import MovieListing, MovieShowing, WebScraper

ALAMO_SF_URL = "https://drafthouse.com/sf"
ALAMO_SF_THEATER = "alamo_drafthouse_sf"
ALAMO_SF_THEATER_LINK = "https://drafthouse.com/sf/theater/new-mission"
ALAMO_SF_AREA = "mission"
ALAMO_SF_MAP = "https://maps.google.com/?q=2550+Mission+St,+San+Francisco,+CA+94110"


def _extract_text(html: str) -> str:
    """Strip HTML tags from a string."""
    return re.sub(r"<[^>]+>", " ", html).strip()


class AlamoScraper(WebScraper):
    """
    Extends WebScraper to add Alamo Drafthouse SF scraping.
    Writes into the same self.listings dict so save_json works unchanged.
    """

    def scrape_alamo_sf(self, driver: WebDriver) -> None:
        """
        Main entry point. Call after scraping Veezi theaters so all data
        ends up in self.listings before save_json is called.
        """
        slugs = self._get_all_sf_slugs(driver)
        print(f"Alamo SF: found {len(slugs)} show(s)")

        for slug in slugs:
            print(f"  Scraping: {slug}")
            try:
                self._scrape_show_page(driver, slug)
            except Exception as e:
                print(f"    Failed: {e}")

    # ------------------------------------------------------------------
    # Step 1 — discover all SF slugs by iterating every available date
    # ------------------------------------------------------------------

    def _get_all_sf_slugs(self, driver: WebDriver) -> list[str]:
        """
        Load the SF landing page, apply the 'San Francisco' WHERE filter,
        then click every available date to collect all unique show slugs.
        Returns a deduplicated list in discovery order.
        """
        driver.get(ALAMO_SF_URL)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CLASS_NAME, "show-me-slider-item"))
        )
        time.sleep(2)

        # Apply SF location filter
        for item in driver.find_elements(By.CLASS_NAME, "show-me-slider-item"):
            if (item.get_attribute("textContent") or "").strip() == "San Francisco":
                driver.execute_script("arguments[0].click();", item)
                break
        time.sleep(1.5)

        # Collect all WHEN date buttons (contain m/d pattern)
        date_buttons = [
            item
            for item in driver.find_elements(By.CLASS_NAME, "show-me-slider-item")
            if re.search(r"\d+/\d+", item.get_attribute("textContent") or "")
        ]
        print(f"  Alamo SF: scanning {len(date_buttons)} dates...")

        seen: dict[str, None] = {}  # ordered set via dict
        try:
            section = driver.find_element(By.ID, "now-playing")
        except NoSuchElementException:
            return []

        for btn in date_buttons:
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(1.2)
            for card in section.find_elements(By.CLASS_NAME, "adc-show-card"):
                slug = self._card_slug(card)
                if slug:
                    seen[slug] = None

        return list(seen.keys())

    @staticmethod
    def _card_slug(card) -> str:
        """Extract slug from the card's img src URL."""
        for img in card.find_elements(By.TAG_NAME, "img"):
            src = img.get_attribute("src") or ""
            m = re.search(r"/images/shows/([^/?]+)", src)
            if m:
                return m.group(1)
            m = re.search(r"/images/events/([^/?]+)", src)
            if m:
                return m.group(1)
        return ""

    # ------------------------------------------------------------------
    # Step 2 — scrape an individual show page for dates + showtimes
    # ------------------------------------------------------------------

    def _scrape_show_page(self, driver: WebDriver, slug: str) -> None:
        """Visit /sf/show/{slug} and collect showtimes per date for the SF location."""
        show_url = f"https://drafthouse.com/sf/show/{slug}"
        driver.get(show_url)

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "adc-show-time-slider"))
            )
        except TimeoutException:
            # Try the event URL
            show_url = f"https://drafthouse.com/sf/event/{slug}"
            driver.get(show_url)
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, "adc-show-time-slider")
                    )
                )
            except TimeoutException:
                return

        time.sleep(1.5)

        title = self._get_show_title(driver) or slug.replace("-", " ").title()
        poster_key = self._download_poster(driver, title)
        rating = self._get_rating(driver)
        self._select_sf_location(driver)
        time.sleep(0.5)

        pacific_tz = pytz.timezone("US/Pacific")
        today = (
            datetime.now(pacific_tz)
            if self.today is None
            else pacific_tz.localize(self.today)
        )

        # Determine how many date tabs exist once, then re-fetch buttons each
        # iteration to avoid stale element references after Angular re-renders.
        n_dates = len(self._get_date_buttons(driver))

        for i in range(n_dates):
            # Re-find buttons on every iteration — Angular re-renders the slider
            # after each click, making previously stored references stale.
            date_buttons = self._get_date_buttons(driver)
            if i >= len(date_buttons):
                break
            date_str, btn = date_buttons[i]

            date = self._parse_alamo_date(date_str, today)
            if not date:
                continue

            driver.execute_script("arguments[0].click();", btn)
            time.sleep(1.2)

            showtime_pairs = self._get_showtimes(driver)
            if not showtime_pairs:
                continue

            showings = []
            for t, sold_out in showtime_pairs:
                time_24 = self._parse_12h_time(t)
                if time_24:
                    available = "SOLD OUT" if sold_out else ""
                    showings.append(
                        MovieShowing(available=available, link=show_url, time=time_24)
                    )

            if not showings:
                continue

            listing = MovieListing(
                showings=showings,
                theater=ALAMO_SF_THEATER,
                map=ALAMO_SF_MAP,
                area=ALAMO_SF_AREA,
                theater_link=ALAMO_SF_THEATER_LINK,
            )

            date_dict = self.listings.get(date, {})
            title_dict = date_dict.get(title, {})
            if not title_dict:
                title_dict = {"poster": poster_key, "rating": rating}

            listings_list = title_dict.get("listings", [])
            listings_list.append(listing)
            title_dict["listings"] = listings_list
            date_dict[title] = title_dict
            self.listings[date] = date_dict

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _download_poster(self, driver: WebDriver, title: str) -> str:
        """
        Download the show poster image if it doesn't exist yet.
        Returns the base64-encoded poster key used as the filename.
        """
        poster_key = base64.urlsafe_b64encode(title.lower().encode()).decode("utf-8")
        save_path = self.poster_dir / f"{poster_key}.png"
        save_path.parent.mkdir(exist_ok=True, parents=True)

        if not save_path.exists():
            # Grab the first non-lazy-loaded img with a drafthouse.com src
            imgs = driver.find_elements(By.TAG_NAME, "img")
            for img in imgs:
                src = img.get_attribute("src") or ""
                if "img-assets.drafthouse.com" in src:
                    try:
                        data = requests.get(src, timeout=10).content
                        save_path.write_bytes(data)
                    except Exception:
                        pass
                    break

        return poster_key

    @staticmethod
    def _get_show_title(driver: WebDriver) -> str:
        """Extract the canonical title from the show page h1."""
        try:
            el = driver.find_element(By.CSS_SELECTOR, "show-title")
            return (el.get_attribute("textContent") or "").strip()
        except NoSuchElementException:
            pass
        try:
            h1 = driver.find_element(
                By.CSS_SELECTOR, ".adc-show-time-section__show-title"
            )
            return (h1.get_attribute("textContent") or "").strip()
        except NoSuchElementException:
            return ""

    @staticmethod
    def _get_rating(driver: WebDriver) -> str:
        """Extract rating from the show details line (e.g. 'Rated PG-13 • 156 min')."""
        try:
            details = driver.find_element(
                By.CSS_SELECTOR, ".adc-show-time-section__show-details"
            )
            text = details.get_attribute("innerHTML") or ""
            # e.g. "Rated PG-13 • 156 min •  2026"
            m = re.search(r"Rated\s+([A-Z0-9-]+)", text)
            return m.group(1) if m else ""
        except NoSuchElementException:
            return ""

    @staticmethod
    def _select_sf_location(driver: WebDriver) -> None:
        """Click the 'San Francisco' location button if it isn't already active."""
        try:
            sliders = driver.find_elements(By.CLASS_NAME, "adc-show-time-slider")
            for slider in sliders:
                items = slider.find_elements(By.CLASS_NAME, "adc-slider-item")
                for item in items:
                    classes = item.get_attribute("class") or ""
                    tc = item.get_attribute("textContent") or ""
                    if (
                        "San Francisco" in tc
                        and "adc-slider-item--active" not in classes
                    ):
                        driver.execute_script("arguments[0].click();", item)
                        return
        except Exception:
            pass

    @staticmethod
    def _get_date_buttons(driver: WebDriver) -> list[tuple[str, object]]:
        """
        Find the date-selector slider and return [(date_str, button_element)].
        date_str is a clean "m/d" string (e.g. "4/1") extracted from innerHTML
        to avoid the textContent concatenation bug where hidden/visible child
        divs merge into ambiguous strings like "WednesdayWed 4/14/1".
        """
        sliders = driver.find_elements(By.CLASS_NAME, "adc-show-time-slider")
        for slider in sliders:
            btns = slider.find_elements(By.CLASS_NAME, "adc-slider-item")
            if not btns:
                continue
            # Date buttons contain nested divs with m/d dates; detect by innerHTML
            sample_html = btns[0].get_attribute("innerHTML") or ""
            if not re.search(r"\d+/\d+", sample_html):
                continue
            result = []
            for btn in btns:
                # Use innerHTML — HTML tags keep each div's text separate,
                # preventing "Wed 4/1" + "4/1" from merging into "4/14/1".
                inner = btn.get_attribute("innerHTML") or ""
                date_matches = re.findall(r"(\d{1,2}/\d{1,2})", inner)
                date_str = date_matches[-1] if date_matches else ""
                result.append((date_str, btn))
            return result
        return []

    @staticmethod
    def _get_showtimes(driver: WebDriver) -> list[tuple[str, bool]]:
        """
        Return (time_str, is_sold_out) pairs from the wrapped showtime slider.
        Struck-through slots are included as sold-out; disabled slots are skipped.
        """
        try:
            wrapped = driver.find_element(
                By.CSS_SELECTOR, ".adc-show-time-slider__items--wrapped"
            )
        except NoSuchElementException:
            return []

        items = wrapped.find_elements(By.CLASS_NAME, "adc-slider-item")
        times = []
        for item in items:
            classes = item.get_attribute("class") or ""
            if "adc-slider-item--disabled" in classes:
                continue
            sold_out = "adc-slider-item--strike-through" in classes
            tc = (item.get_attribute("textContent") or "").strip()
            if re.match(r"\d+:\d+[ap]m", tc, re.IGNORECASE):
                times.append((tc, sold_out))
        return times

    @staticmethod
    def _parse_alamo_date(date_str: str, today: datetime) -> str | None:
        """
        Parse a clean "m/d" date string (e.g. "4/1", "3/28") into YYYY-MM-DD.
        The date_str comes pre-cleaned from _get_date_buttons via innerHTML parsing.
        """
        m = re.match(r"(\d{1,2})/(\d{1,2})$", date_str.strip())
        if not m:
            return None
        month, day = int(m.group(1)), int(m.group(2))
        year = today.year
        try:
            candidate = datetime(year, month, day, tzinfo=today.tzinfo)
        except ValueError:
            return None
        if candidate < today - timedelta(days=1):
            year += 1
        return f"{year}-{month:02d}-{day:02d}"

    @staticmethod
    def _parse_12h_time(time_str: str) -> str | None:
        """Convert '9:30pm' → '2130', '12:00pm' → '1200'."""
        time_str = time_str.strip().lower()
        for fmt in ("%I:%M%p", "%I%p"):
            try:
                return datetime.strptime(time_str, fmt).strftime("%H%M")
            except ValueError:
                continue
        return None
