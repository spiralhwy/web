"""
Unit tests to ensure that web scraper is properly configured.
"""

import json
import os
import shutil
from pathlib import Path

import pytest
from hydra import compose, initialize
from omegaconf import DictConfig

from spiral_hwy.tools.web_scraper import WebScraper, get_driver, go_to_website

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
    # get config
    with initialize(version_base=None, config_path="../configs"):
        config = compose(config_name="main", overrides=["veezi=test"])

    poster_dir = K_TMP_TEST_DIR / "posters"

    # scrape websites
    ws = WebScraper(poster_dir=poster_dir)
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
    ground_truth_dir = Path(__file__) / "ground_truth" / "veezi"
    assert read_json(json_path) == read_json(ground_truth_dir / "movies.json")

    # Check posters are save correctly
    poster_files = sorted(os.listdir(poster_dir))
    assert poster_files == read_json(ground_truth_dir / "posters.json")

    # destroy assets
    json_path.unlink()
    shutil.rmtree(K_TMP_TEST_DIR)
