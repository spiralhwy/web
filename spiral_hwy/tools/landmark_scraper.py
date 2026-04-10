#!/usr/bin/env python3
"""
Scraper for Landmark Opera Plaza Cinema showtimes.

Architecture:
1. Load https://www.landmarktheatres.com/showtimes/
2. Select "Opera Plaza Cinema" from the theater selector.
3. Iterate through available date buttons, collect movies and showtimes.
"""

import base64
import re
import time
from datetime import datetime, timedelta

import pytz
import requests
from alamo_scraper import AlamoScraper
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from web_scraper import MovieListing, MovieShowing

LANDMARK_SHOWTIMES_URL = "https://www.landmarktheatres.com/showtimes/"
LANDMARK_THEATER_ID = "X00U8"
LANDMARK_THEATER = "landmark_opera_plaza"
LANDMARK_THEATER_LINK = (
    "https://www.landmarktheatres.com/san-francisco/opera-plaza-cinema"
)
LANDMARK_AREA = "civic_center"
LANDMARK_MAP = "https://maps.app.goo.gl/kqZu2DAkUSAYxtrP9"


class LandmarkScraper(AlamoScraper):
    """
    Extends AlamoScraper (which extends WebScraper) to add Landmark
    Opera Plaza Cinema scraping. Writes into the same self.listings
    dict so save_json works unchanged.
    """

    def scrape_landmark(self, driver: WebDriver) -> None:
        """
        Main entry point. Call after scraping other theaters so all data
        ends up in self.listings before save_json is called.
        """
        driver.get(LANDMARK_SHOWTIMES_URL)

        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//*[contains(text(), 'Please select a location') or contains(text(), 'select a location')]",
                    )
                )
            )
        except TimeoutException:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "button, [role='button']")
                    )
                )
            except TimeoutException:
                print("  Landmark: timed out waiting for theater selector")
                return

        time.sleep(2)
        self._select_theater(driver)
        time.sleep(3)

        pacific_tz = pytz.timezone("US/Pacific")
        today = (
            datetime.now(pacific_tz)
            if self.today is None
            else pacific_tz.localize(self.today)
        )

        # Iterate through date buttons, scraping movies for each date
        date_buttons = self._get_landmark_date_buttons(driver)
        print(f"  Landmark Opera Plaza: found {len(date_buttons)} date(s)")

        for i, (date_str, _btn) in enumerate(date_buttons):
            buttons = self._get_landmark_date_buttons(driver)
            if i >= len(buttons):
                break
            date_str, btn = buttons[i]

            date = self._parse_date(date_str, today)
            if not date:
                continue

            driver.execute_script("arguments[0].click();", btn)
            time.sleep(2)

            movies = self._get_movies(driver)
            if not movies:
                continue

            self._store_movies(date, movies)

    def _store_movies(self, date: str, movies: list) -> None:
        """Store extracted movies into self.listings for a given date."""
        for title, rating, poster_src, showtime_pairs in movies:
            poster_key = self._download_poster_from_src(poster_src, title)

            showings = []
            for t, link, sold_out in showtime_pairs:
                time_24 = self._parse_12h_time(t)
                if time_24:
                    available = "SOLD OUT" if sold_out else ""
                    showings.append(
                        MovieShowing(available=available, link=link, time=time_24)
                    )

            if not showings:
                continue

            listing = MovieListing(
                showings=showings,
                theater=LANDMARK_THEATER,
                map=LANDMARK_MAP,
                area=LANDMARK_AREA,
                theater_link=LANDMARK_THEATER_LINK,
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
    # Theater selection
    # ------------------------------------------------------------------

    @staticmethod
    def _select_theater(driver: WebDriver) -> None:
        """Click the theater selector and choose Opera Plaza Cinema."""
        # Click the location trigger to open the dropdown.
        # The real site has two buttons containing "select a location":
        #   button[0] text="Showtimes for:Please select a location—"
        #   button[9] text="At:Please select a location"
        # We want the "At:" one which is the in-page theater picker.
        trigger = None
        for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
            text = (btn.get_attribute("textContent") or "").lower()
            if "select a location" in text or "select a theater" in text:
                trigger = btn
                # Prefer the shorter / "At:" variant if present
                if "at:" in text:
                    break

        if trigger:
            driver.execute_script("arguments[0].click();", trigger)
            time.sleep(1.5)
        else:
            return

        # Click "Opera Plaza" in the opened dropdown
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(), 'Opera Plaza')]")
                )
            )
        except TimeoutException:
            pass

        elems = driver.find_elements(By.XPATH, "//*[contains(text(), 'Opera Plaza')]")
        for elem in elems:
            try:
                driver.execute_script("arguments[0].click();", elem)
                time.sleep(2)
                return
            except Exception:
                continue

    # ------------------------------------------------------------------
    # Date navigation
    # ------------------------------------------------------------------

    @staticmethod
    def _get_landmark_date_buttons(driver: WebDriver) -> list[tuple[str, object]]:
        """
        Find date selector buttons. Returns [(date_text, button_element)].
        The Landmark Gatsby site uses date-selector buttons styled as tabs.
        """
        result = []
        # Try various selectors for date buttons
        selectors = [
            "[class*='DateSelector'] button",
            "[class*='date-selector'] button",
            "[class*='PeriodSelector'] button",
            "[class*='DaySelector'] button",
            "[class*='period-selector'] button",
        ]
        for sel in selectors:
            buttons = driver.find_elements(By.CSS_SELECTOR, sel)
            if buttons:
                for btn in buttons:
                    text = " ".join(
                        (btn.get_attribute("textContent") or "").split()
                    ).strip()
                    if text:
                        result.append((text, btn))
                if result:
                    return result

        # Fallback: look for date-like text in any clickable elements
        for btn in driver.find_elements(
            By.CSS_SELECTOR, "button, [role='tab'], [class*='day']"
        ):
            text = " ".join((btn.get_attribute("textContent") or "").split()).strip()
            if re.search(
                r"\d{1,2}/\d{1,2}|\w+day|today|tomorrow"
                r"|^(mon|tue|wed|thu|fri|sat|sun)\s*\d{1,2}$",
                text,
                re.I,
            ):
                result.append((text, btn))

        return result

    # ------------------------------------------------------------------
    # Movie extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _get_movies(
        driver: WebDriver,
    ) -> list[tuple[str, str, str, list[tuple[str, str, bool]]]]:
        """
        Extract movies from the current page view.
        Returns [(title, rating, poster_src, [(time_str, ticket_link, is_sold_out)])].

        Uses JavaScript to walk up from each showtime link to find the
        nearest ancestor that contains a movie poster image. This avoids
        relying on CSS class names which change with site rebuilds.
        """
        # First try class-name selectors (works for test fixtures)
        movies = _get_movies_by_class(driver)
        if movies:
            return movies

        # Structural approach for the real site: extract via JS
        raw = driver.execute_script(
            r"""
            var SKIP_ALTS = ['Spinner', 'Landmark', 'decorative'];
            function isMovieImg(img) {
                var alt = (img.alt || '').trim();
                if (alt.length < 2) return false;
                for (var i = 0; i < SKIP_ALTS.length; i++) {
                    if (alt.indexOf(SKIP_ALTS[i]) !== -1) return false;
                }
                return true;
            }

            // Find all showtime links (a tags with time-like text)
            var allLinks = document.querySelectorAll('a');
            var timeRe = /^\d{1,2}:\d{2}\s*[APap][Mm]$/;
            var movieMap = {};  // title -> {poster, rating, showtimes}

            for (var i = 0; i < allLinks.length; i++) {
                var link = allLinks[i];
                var timeText = link.textContent.trim();
                if (!timeRe.test(timeText)) continue;

                var href = link.href || '';
                var cls = link.className || '';
                var soldOut = /sold.?out|disabled|unavailable/i.test(cls);

                // Walk up to find movie container with poster img
                var el = link;
                var title = null;
                var posterSrc = '';
                for (var j = 0; j < 15; j++) {
                    el = el.parentElement;
                    if (!el) break;
                    var imgs = el.querySelectorAll('img');
                    for (var k = 0; k < imgs.length; k++) {
                        if (isMovieImg(imgs[k])) {
                            title = imgs[k].alt.trim();
                            posterSrc = imgs[k].src || '';
                            break;
                        }
                    }
                    if (title) break;
                }
                if (!title) continue;

                if (!movieMap[title]) {
                    // Try to find rating in the movie container text
                    var containerText = el ? el.textContent : '';
                    var ratingMatch = containerText.match(/\b(NC-17|PG-13|PG|NR|UR|R|G)\b/);
                    movieMap[title] = {
                        poster: posterSrc,
                        rating: ratingMatch ? ratingMatch[1] : '',
                        showtimes: []
                    };
                }
                movieMap[title].showtimes.push({
                    time: timeText, href: href, soldOut: soldOut
                });
            }

            var result = [];
            for (var t in movieMap) {
                var m = movieMap[t];
                result.push({title: t, rating: m.rating, poster: m.poster, showtimes: m.showtimes});
            }
            return result;
        """
        )

        movies = []
        for entry in raw:
            showtime_pairs = [
                (s["time"], s["href"], s["soldOut"]) for s in entry["showtimes"]
            ]
            if showtime_pairs:
                movies.append(
                    (entry["title"], entry["rating"], entry["poster"], showtime_pairs)
                )
        return movies

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _download_poster_from_src(self, poster_src: str, title: str) -> str:
        """
        Download the poster image if it doesn't exist yet.
        Returns the base64-encoded poster key.
        """
        poster_key = base64.urlsafe_b64encode(title.lower().encode()).decode("utf-8")
        save_path = self.poster_dir / f"{poster_key}.png"
        save_path.parent.mkdir(exist_ok=True, parents=True)

        if not save_path.exists() and poster_src:
            try:
                data = requests.get(poster_src, timeout=10).content
                save_path.write_bytes(data)
            except Exception:
                pass

        return poster_key

    @staticmethod
    def _parse_date(date_text: str, today: datetime) -> str | None:
        """
        Parse a date button label into YYYY-MM-DD.
        Handles formats like "Today", "Tomorrow", "Wed 4/2", "Thu Apr 3", "4/2".
        """
        text = date_text.strip().lower()

        if text == "today":
            return today.strftime("%Y-%m-%d")

        if text == "tomorrow":
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")

        # Try "m/d" or "dayname m/d" pattern
        m = re.search(r"(\d{1,2})/(\d{1,2})", text)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            year = today.year
            try:
                candidate = datetime(year, month, day, tzinfo=today.tzinfo)
            except ValueError:
                return None
            if candidate < today - timedelta(days=1):
                year += 1
            return f"{year}-{month:02d}-{day:02d}"

        # Try "dayname Mon DD" pattern (e.g., "Wed Apr 2")
        month_names = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        m = re.search(r"([a-z]{3})\s+(\d{1,2})", text)
        if m:
            mon_str, day_str = m.group(1), m.group(2)
            month = month_names.get(mon_str[:3])
            if month:
                day = int(day_str)
                year = today.year
                try:
                    candidate = datetime(year, month, day, tzinfo=today.tzinfo)
                except ValueError:
                    return None
                if candidate < today - timedelta(days=1):
                    year += 1
                return f"{year}-{month:02d}-{day:02d}"

        # Try "DayAbbrev DD" pattern (e.g., "Sat 4", "Sat4", "Wed 9") — bare day number
        day_abbrevs = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        day_abbrev_to_weekday = {
            "mon": 0,
            "tue": 1,
            "wed": 2,
            "thu": 3,
            "fri": 4,
            "sat": 5,
            "sun": 6,
        }
        m = re.match(r"([a-z]{3})\s*(\d{1,2})$", text)
        if m and m.group(1) in day_abbrevs:
            day = int(m.group(2))
            expected_weekday = day_abbrev_to_weekday[m.group(1)]
            # Find the nearest future date matching both day-of-month and weekday
            for offset in range(0, 90):
                candidate = today + timedelta(days=offset)
                if candidate.day == day and candidate.weekday() == expected_weekday:
                    return candidate.strftime("%Y-%m-%d")

        return None

    @staticmethod
    def _parse_12h_time(time_str: str) -> str | None:
        """Convert '9:30pm' or '9:30 PM' → '2130'."""
        time_str = re.sub(r"\s+", "", time_str.strip().lower())
        for fmt in ("%I:%M%p", "%I%p"):
            try:
                return datetime.strptime(time_str, fmt).strftime("%H%M")
            except ValueError:
                continue
        return None


# ------------------------------------------------------------------
# Module-level helpers for extracting data from movie cards
# ------------------------------------------------------------------


def _get_movies_by_class(driver):
    """Try to find movies using semantic class-name selectors (test fixtures)."""
    card_selectors = [
        "[class*='MovieCard']",
        "[class*='movie-card']",
        "[class*='ShowtimeMovie']",
        "[class*='showtime-movie']",
        "[class*='MovieRow']",
    ]
    cards = []
    for sel in card_selectors:
        cards = driver.find_elements(By.CSS_SELECTOR, sel)
        if cards:
            break
    if not cards:
        return []

    movies = []
    for card in cards:
        title = _extract_title(card)
        if not title:
            continue
        rating = _extract_rating(card)
        poster_src = _extract_poster_src(card)
        showtime_pairs = _extract_showtimes(card)
        if showtime_pairs:
            movies.append((title, rating, poster_src, showtime_pairs))
    return movies


def _extract_title(card) -> str:
    """Extract movie title from a card element."""
    selectors = [
        "[class*='Title'] h2",
        "[class*='title'] h2",
        "[class*='MovieTitle']",
        "h2",
        "h3",
    ]
    for sel in selectors:
        try:
            elem = card.find_element(By.CSS_SELECTOR, sel)
            text = (elem.get_attribute("textContent") or "").strip()
            if text:
                return text
        except NoSuchElementException:
            continue
    return ""


def _extract_rating(card) -> str:
    """Extract rating from a card element."""
    selectors = [
        "[class*='Rating']",
        "[class*='rating']",
        "[class*='Certificate']",
        "[class*='certificate']",
        "[class*='TechInfo']",
    ]
    for sel in selectors:
        try:
            elem = card.find_element(By.CSS_SELECTOR, sel)
            text = (elem.get_attribute("textContent") or "").strip()
            m = re.search(r"(G|PG-13|PG|R|NC-17|NR|UR)", text)
            if m:
                return m.group(1)
        except NoSuchElementException:
            continue
    return ""


def _extract_poster_src(card) -> str:
    """Extract poster image URL from a card element."""
    try:
        img = card.find_element(By.CSS_SELECTOR, "img")
        return img.get_attribute("src") or ""
    except NoSuchElementException:
        return ""


def _extract_showtimes(card) -> list[tuple[str, str, bool]]:
    """
    Extract showtimes from a card element.
    Returns [(time_str, ticket_link, is_sold_out)].
    """
    times = []
    # Try finding showtime buttons/links
    selectors = [
        "[class*='Showtime'] a",
        "[class*='showtime'] a",
        "[class*='Showtime'] button",
        "[class*='SessionButton']",
        "[class*='session-button']",
        "a[href*='ticket']",
        "a[href*='booking']",
    ]
    items = []
    for sel in selectors:
        items = card.find_elements(By.CSS_SELECTOR, sel)
        if items:
            break

    if not items:
        # Broader fallback: any element with time-like text
        for elem in card.find_elements(By.CSS_SELECTOR, "a, button"):
            text = (elem.get_attribute("textContent") or "").strip()
            if re.match(r"\d{1,2}:\d{2}\s*[ap]m", text, re.I):
                items.append(elem)

    for item in items:
        text = (item.get_attribute("textContent") or "").strip()
        if not re.match(r"\d{1,2}:\d{2}\s*[ap]m", text, re.I):
            continue

        link = item.get_attribute("href") or ""
        classes = item.get_attribute("class") or ""
        sold_out = any(
            kw in classes.lower()
            for kw in ["sold-out", "soldout", "disabled", "unavailable"]
        )
        times.append((text, link, sold_out))

    return times
