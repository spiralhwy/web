"""
Unit tests to ensure that web scraper is properly configured.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import pytz
from hydra import compose, initialize
from omegaconf import DictConfig
from selenium.webdriver.common.by import By

from spiral_hwy.tools.alamo_scraper import AlamoScraper
from spiral_hwy.tools.web_scraper import (
    MovieShowing,
    WebScraper,
    get_driver,
    go_to_website,
)

K_TMP_TEST_DIR = Path("/tmp/spiral-hwy-test")


def read_json(path: Path | str):
    """
    Get JSON contents.
    """
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def test_veezi():
    """
    Test scrape of Veezi format.
    """
    # destroy old assets
    if K_TMP_TEST_DIR.exists():
        shutil.rmtree(K_TMP_TEST_DIR)

    # get config
    with initialize(version_base=None, config_path="../configs"):
        config = compose(config_name="main", overrides=["veezi=test"])

    poster_dir = K_TMP_TEST_DIR / "posters"

    # scrape websites
    ws = WebScraper(
        today=datetime(year=2024, month=12, day=9), year=2024, poster_dir=poster_dir
    )
    layout: DictConfig = config.veezi.dates_list
    first_element = layout[0]
    driver = get_driver()
    for w in config.veezi.websites:
        print(f"---------- scrape {w.theater} ----------")
        website_path = "file:///" + str(Path(__file__).parent / w.showings)
        go_to_website(driver, website_path, first_element)
        ws.scrape(driver, layout, w)
    driver.quit()

    # save listings
    json_path = K_TMP_TEST_DIR / "json" / "movies.json"
    ws.save_json(json_path)

    # check that JSONs are equivalent
    ground_truth_dir = Path(__file__).parent / "ground_truth" / "veezi"
    assert read_json(json_path) == read_json(ground_truth_dir / "movies.json")

    # Check posters are save correctly
    poster_files = sorted(os.listdir(poster_dir))
    assert poster_files == read_json(ground_truth_dir / "posters.json")

    # destroy assets
    shutil.rmtree(K_TMP_TEST_DIR)


def test_3d_title():
    """
    Test that 3D movie titles are properly cleaned:
    - HTML tags like <i class="icon-3d"></i> are stripped
    - " [3D]" is appended when icon-3d is detected
    - &amp; is decoded
    - Whitespace is normalized
    """
    ws = WebScraper()

    def make_listing(title: str) -> str:
        """Push a listing through _create_listing and return the cleaned title."""
        ws.showings = [MovieShowing(available="", link="http://test", time="1930")]
        ws.assets.update(
            {
                "title": title,
                "date": "2026-04-01",
                "poster": "test",
                "rating": "PG-13",
                "theater": "t",
                "map": "m",
                "area": "a",
                "theater_link": "l",
            }
        )
        ws._create_listing(None, None)
        return list(ws.listings["2026-04-01"].keys())[-1]

    # 3D icon tag → stripped and " [3D]" appended
    assert make_listing('Thunderbolts* <i class="icon-3d"></i>') == "Thunderbolts* [3D]"

    # Multi-line 3D title (as seen in live data for Inferno)
    assert (
        make_listing('Inferno\n                    <i class="icon-3d"></i>')
        == "Inferno [3D]"
    )

    # Regular title — no changes
    assert make_listing("Project Hail Mary") == "Project Hail Mary"

    # HTML entity decoding
    assert make_listing("Tom &amp; Jerry") == "Tom & Jerry"

    # Title with other HTML tags — stripped but no 3D suffix
    assert make_listing("Title <b>Bold</b>") == "Title Bold"


def test_alamo():
    """
    Test Alamo Drafthouse SF scraper: date parsing, time parsing,
    date button extraction (innerHTML), showtime/sold-out detection,
    and slug extraction from show cards.
    """
    pacific_tz = pytz.timezone("US/Pacific")
    today = pacific_tz.localize(datetime(2026, 3, 28))

    # ------------------------------------------------------------------
    # _parse_alamo_date — clean "m/d" strings from innerHTML
    # ------------------------------------------------------------------
    parse = AlamoScraper._parse_alamo_date

    # Standard dates
    assert parse("3/28", today) == "2026-03-28"
    assert parse("3/29", today) == "2026-03-29"
    assert parse("4/10", today) == "2026-04-10"
    assert parse("12/25", today) == "2026-12-25"

    # Single-digit days (the original bug — "4/1" was lost when textContent
    # concatenated "Wed 4/1" + "4/1" into "4/14/1", parsed as month 14)
    assert parse("4/1", today) == "2026-04-01"
    assert parse("3/1", today) == "2027-03-01"  # past → rolls to next year
    assert parse("4/9", today) == "2026-04-09"

    # Yesterday is still valid (within 1-day tolerance)
    assert parse("3/27", today) == "2026-03-27"

    # Two days ago rolls to next year
    assert parse("3/26", today) == "2027-03-26"

    # Year rollover — January is in the past relative to March
    assert parse("1/15", today) == "2027-01-15"

    # Invalid inputs
    assert parse("", today) is None
    assert parse("Wednesday", today) is None
    assert parse("13/1", today) is None  # invalid month
    assert parse("2/30", today) is None  # invalid day

    # ------------------------------------------------------------------
    # _parse_12h_time
    # ------------------------------------------------------------------
    parse_t = AlamoScraper._parse_12h_time

    assert parse_t("9:30pm") == "2130"
    assert parse_t("9:30am") == "0930"
    assert parse_t("12:00pm") == "1200"
    assert parse_t("12:00am") == "0000"
    assert parse_t("1:15am") == "0115"
    assert parse_t("11:45pm") == "2345"
    assert parse_t("invalid") is None

    # ------------------------------------------------------------------
    # Selenium fixture tests
    # ------------------------------------------------------------------
    driver = get_driver()
    try:
        fixtures = Path(__file__).parent / "websites" / "alamo_sf"

        # --- Show page fixture ---
        driver.get("file:///" + str(fixtures / "show_page.html"))

        # _get_date_buttons: should extract clean dates from innerHTML,
        # not the concatenated textContent that caused the April 1st bug.
        date_buttons = AlamoScraper._get_date_buttons(driver)
        date_strs = [d for d, _btn in date_buttons]
        assert date_strs == ["3/28", "3/29", "4/1", "4/10", "12/5"]

        # Verify the parsed dates are all valid
        parsed_dates = [parse(d, today) for d in date_strs]
        assert parsed_dates == [
            "2026-03-28",
            "2026-03-29",
            "2026-04-01",
            "2026-04-10",
            "2026-12-05",
        ]

        # _get_showtimes: should include sold-out, exclude disabled
        showtimes = AlamoScraper._get_showtimes(driver)
        assert showtimes == [
            ("9:30pm", False),  # regular
            ("12:00pm", True),  # sold out (strike-through)
            ("7:00pm", False),  # regular
        ]

        # _get_show_title
        title = AlamoScraper._get_show_title(driver)
        assert title == "Project Hail Mary"

        # _get_rating
        rating = AlamoScraper._get_rating(driver)
        assert rating == "PG-13"

        # _select_sf_location: SF is already active, should be a no-op
        AlamoScraper._select_sf_location(driver)  # should not raise

        # --- Landing page fixture ---
        driver.get("file:///" + str(fixtures / "landing_page.html"))

        cards = driver.find_elements(By.CLASS_NAME, "adc-show-card")
        slugs = [AlamoScraper._card_slug(c) for c in cards]
        assert slugs == [
            "project-hail-mary",
            "twin-peaks-marathon",
            "undertone",
            "",  # unrelated image, no slug
        ]

    finally:
        driver.quit()
