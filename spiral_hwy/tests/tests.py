"""
Unit tests to ensure that web scraper is properly configured.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from hydra import compose, initialize
from omegaconf import DictConfig

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
