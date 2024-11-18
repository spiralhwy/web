#!/usr/bin/env python3

import requests

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
import urllib.request

import hydra
import selenium.webdriver
from omegaconf import DictConfig
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


@dataclass
class MovieShowing:
    available: bool
    link: str
    time: str


@dataclass
class MovieListing:
    date: str
    poster: str
    rating: str
    showings: List[MovieShowing]
    title: str


def catch_optional(func):
    def wrapper(*args, **kwargs):
        if kwargs.get("optional"):
            try:
                return func(*args, **kwargs)
            except NoSuchElementException:
                return None
        else:
            return func(*args, **kwargs)

    return wrapper


ATTRIBUTE_ID = {
    "id": By.ID,
    "class_name": By.CLASS_NAME,
    "css_selector": By.CSS_SELECTOR,
    "tag_name": By.TAG_NAME,
}  # print(a.name, ASSET_GETTER[a.method](element, a))


def element_click(item: WebElement) -> None:
    item.click()


ELEMENT_ACTIONS = {"click": element_click}


def get_element_attribute(element: WebElement, asset: DictConfig) -> str:
    output = element.get_attribute(asset.field)
    if isinstance(output, str):
        return output.strip()
    return output


def get_element_text(item: WebElement, _asset: DictConfig) -> str:
    return item.text.strip()


ASSET_GETTER = {"get_attribute": get_element_attribute, "text_member": get_element_text}


def go_to_website(driver, website, first_element):
    driver.get(website)
    timeout_sec = 180
    WebDriverWait(driver, timeout_sec).until(
        EC.presence_of_element_located((ATTRIBUTE_ID[first_element.by], first_element.field))
    )


def get_driver() -> WebDriver:
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode (no GUI)
    chrome_options.add_argument("--disable-notifications")  # Disable notifications

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    return driver


class WebScraper:

    def __init__(self):
        self.theater: str

        self.assets = {
            "available": "",
            "date": "",
            "link": "",
            "rating": "",
            "time": "",
            "title": "",
        }

        self.showings: List[MovieShowing]
        self.listings: Dict[str, List[MovieListing]] = dict()

        self.SPECIAL = {
            "create_listing": self.create_listing,
            "create_showing": self.create_showing,
            "save_poster": self.save_poster,
        }

    def create_listing(self, element, config):
        if len(self.showings) == 0:
            return

        self.listings[self.theater].append(
            MovieListing(
                deepcopy(self.assets["date"]),
                deepcopy(self.assets["poster"]),
                deepcopy(self.assets["rating"]),
                deepcopy(self.showings),
                deepcopy(self.assets["title"]),
            )
            # )
        )
        self.assets["poster"] = ""
        self.assets["rating"] = ""
        self.showings.clear()
        self.assets["title"] = ""

    def create_showing(self, element, config):
        if not self.assets["link"] or not self.assets["time"]:
            return

        self.showings.append(
            MovieShowing(
                deepcopy(self.assets["available"]),
                deepcopy(self.assets["link"]),
                deepcopy(self.assets["time"]),
            )
        )
        self.assets["available"] = ""
        self.assets["link"] = ""
        self.assets["time"] = ""

    def save_json(self, path: Path):
        path.parent.mkdir(exist_ok=True, parents=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.listings, f, indent=4, default=lambda o: o.__dict__)

    def save_poster(self, element: WebElement, config):
        poster_name: str = ASSET_GETTER[config.asset.method](element, config.asset).lower()

        import base64
        file_name_string = base64.urlsafe_b64encode(poster_name.encode()).decode("utf-8")
        self.assets["poster"] = file_name_string
        
        poster_src = element.get_attribute("src")
        save_path = Path(__file__).parent / "_data" / "posters" / f"{file_name_string}.png"
        save_path.parent.mkdir(exist_ok=True, parents=True)
        save_path = str(save_path)




        img_data = requests.get(poster_src).content
        with open(save_path, 'wb') as handler:
            handler.write(img_data)


    def scrape(self, root: WebDriver | WebElement, config: DictConfig, theater: str) -> None:
        self.theater = theater
        self.showings = list()
        self.listings[self.theater] = list()
        self.unpack_list(root, config)

    @catch_optional
    def unpack_element(self, root: WebDriver | WebElement, attribute_id, config: DictConfig, **kwargs) -> None:
        """
        Unpack single element.
        """
        if config.get("child"):
            elements = root.find_elements(attribute_id, config.field)
            for e in elements:

                self.unpack_list(e, config.child)

                if config.get("child_special"):
                    self.SPECIAL[config.child_special](e, config)

        else:
            element = root.find_element(attribute_id, config.field)
            if config.get("action"):
                for a in config.action:
                    ELEMENT_ACTIONS[a](element)

            if config.get("asset"):
                a = config.asset
                self.assets[a.name] = ASSET_GETTER[a.method](element, a)

            if config.get("special"):
                self.SPECIAL[config.special](element, config)

    @catch_optional
    def unpack_list(self, root: WebDriver | WebElement, config: DictConfig) -> None:
        """
        Unpack config list.
        """
        for c in config:
            self.unpack_element(root, ATTRIBUTE_ID[c.by], c, optional=c.get("optional", False))




@hydra.main(version_base=None, config_path="configs", config_name="main")
def main(config: DictConfig):

    ws = WebScraper()

    cinema_sf_layout: DictConfig = config.cinema_sf.dates_list
    cinema_sf_first_element = cinema_sf_layout[0]

    try:
        driver = get_driver()
        for w in config.cinema_sf.websites:
            try:
                print(f"---------- scrape {w.theater} ----------")
                go_to_website(driver, w.link, cinema_sf_first_element)
                ws.scrape(driver, cinema_sf_layout, w.theater)
            except:
                print(f"---------- scrape failed {w.theater} ----------")
                driver = get_driver()
        
        json_path = Path(__file__).parent / "_data/movies.json"
        ws.save_json(json)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
