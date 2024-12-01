#!/usr/bin/env python3

import requests

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import time
from datetime import datetime, timedelta
import base64


import hydra
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
    theater: str
    title: str
    map: str
    area: str
    theater_link: str


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
}


def element_click(element: WebElement) -> None:
    element.click()


ELEMENT_ACTIONS = {"click": element_click}


def get_element_attribute(element: WebElement, asset: DictConfig) -> str:
    output = element.get_attribute(asset.field)
    if isinstance(output, str):
        return output.strip()
    return output


def get_element_text(item: WebElement, _asset: DictConfig) -> str:
    return item.text.strip()


def fandango_get_rating(element: WebElement, asset: DictConfig) -> str:
    output = get_element_attribute(element, asset)
    return output.split(",")[0]


ASSET_GETTER = {
    "get_attribute": get_element_attribute,
    "text_member": get_element_text,
    "fandango_get_rating": fandango_get_rating,
}


def go_to_website(driver, website, first_element):
    driver.get(website)
    timeout_sec = 60
    WebDriverWait(driver, timeout_sec).until(
        EC.presence_of_element_located(
            (ATTRIBUTE_ID[first_element.by], first_element.field)
        )
    )
    element = driver.find_element(ATTRIBUTE_ID[first_element.by], first_element.field)
    driver.execute_script("arguments[0].scrollIntoView(true);", element)
    time.sleep(0.5)


def get_driver() -> WebDriver:
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode (no GUI)
    chrome_options.add_argument("--disable-notifications")  # Disable notifications

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=chrome_options
    )

    return driver


class WebScraper:

    def __init__(self, poster_dir: Path = Path(__file__).parent.parent.parent / "public/posters"):

        self.poster_dir: Path = (
            poster_dir if isinstance(poster_dir, Path) else Path(poster_dir)
        )
        self.assets = {
            "area": "",
            "available": "",
            "date": "",
            "link": "",
            "map": "",
            "rating": "",
            "time": "",
            "theater": "",
            "title": "",
            "theater_link": "",
        }

        self.showings: List[MovieShowing]
        self.listings: Dict[str, List[MovieListing]] = dict()

        self.SPECIAL = {
            "convert_date": self.convert_date,
            "convert_time": self.convert_time,
            "create_listing": self.create_listing,
            "create_showing": self.create_showing,
            "save_poster": self.save_poster,
        }

    def convert_date(self, asset: DictConfig):
        # Get today's date
        today = datetime.now()
        yesterday = today - timedelta(days=1)

        # First try current year
        current_year = today.year
        date_str_with_year = f'{self.assets["date"]} {current_year}'

        try:
            date_obj = datetime.strptime(date_str_with_year, asset.special.format)

            # If the date is before yesterday, add a year
            if date_obj < yesterday:
                date_obj = datetime.strptime(
                    f'{self.assets["date"]} {current_year + 1}', "%A %d, %B %Y"
                )

            self.assets["date"] = date_obj.strftime("%Y%m%d")
        except ValueError as e:
            return f"Error parsing date: {e}"

    def convert_time(self, asset: DictConfig):
        try:
            date_obj = datetime.strptime(self.assets["time"], asset.special.format)
            self.assets["time"] = date_obj.strftime("%H%M")
        except ValueError as e:
            return f"Error parsing time: {e}"

    def create_listing(self, _element: WebElement, _config: DictConfig):
        if len(self.showings) == 0:
            return

        listings_of_date = self.listings.get(self.assets["date"], list())
        listings_of_date.append(
            MovieListing(
                self.assets["date"],
                self.assets["poster"],
                self.assets["rating"],
                self.showings.copy(),
                self.assets["theater"],
                self.assets["title"].replace("&amp;", "&"),
                self.assets["map"],
                self.assets["area"],
                self.assets["theater_link"],
            )
        )
        self.listings.update({self.assets["date"]: listings_of_date})
        self.assets["poster"] = ""
        self.assets["rating"] = ""
        self.showings.clear()
        self.assets["title"] = ""

    def create_showing(self, element, config):
        if not self.assets["link"] or not self.assets["time"]:
            return

        self.showings.append(
            MovieShowing(
                self.assets["available"],
                self.assets["link"],
                self.assets["time"],
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
        poster_name: str = ASSET_GETTER[config.asset.method](
            element, config.asset
        ).lower()

        file_name_string = base64.urlsafe_b64encode(poster_name.encode()).decode(
            "utf-8"
        )
        self.assets["poster"] = file_name_string

        poster_src = element.get_attribute("src")
        save_path = self.poster_dir / f"{file_name_string}.png"
        save_path.parent.mkdir(exist_ok=True, parents=True)
        save_path = str(save_path)

        if not Path(save_path).exists():
            if poster_src.startswith("file://"):
                local_path = poster_src[7:]  # Strip off "file://"
                with open(local_path, "rb") as img_file:
                    img_data = img_file.read()
            else:
                img_data = requests.get(poster_src).content

            with open(save_path, "wb") as handler:
                handler.write(img_data)

    def scrape(
        self, root: WebDriver | WebElement, config: DictConfig, website: str
    ) -> None:
        self.assets["theater"] = website.theater
        self.assets["map"] = website.map
        self.assets["area"] = website.area
        self.assets["theater_link"] = website.link
        self.showings = list()
        self.unpack_list(root, config)

    @catch_optional
    def unpack_element(
        self, root: WebDriver | WebElement, attribute_id, config: DictConfig, **kwargs
    ) -> None:
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

                #                 if config.get("actions"):
                # for a in config.actions:

                #     if a.get("asset"):
                #         a = a.asset
                #         self.assets[a.name] = ASSET_GETTER[a.method](element, a)
                #         if a.get("special"):
                #             self.SPECIAL[a.special.method](a)
                #     else:
                #         ELEMENT_ACTIONS[a](element)

            if config.get("asset"):
                a = config.asset
                self.assets[a.name] = ASSET_GETTER[a.method](element, a)
                if a.get("special"):
                    self.SPECIAL[a.special.method](a)

            if config.get("special"):
                self.SPECIAL[config.special](element, config)

    @catch_optional
    def unpack_list(self, root: WebDriver | WebElement, config: DictConfig) -> None:
        """
        Unpack config list.
        """
        for c in config:
            self.unpack_element(
                root, ATTRIBUTE_ID[c.by], c, optional=c.get("optional", False)
            )


@hydra.main(version_base=None, config_path="../configs", config_name="main")
def main(config: DictConfig):

    ws = WebScraper()

    layout: DictConfig = config.veezi.dates_list
    first_element = layout[0]

    # layout: DictConfig = config.fandango.dates_list
    # first_element = layout[0]

    try:
        driver = get_driver()
        for w in config.veezi.websites:
            # try:
                print(f"---------- scrape {w.theater} ----------")
                go_to_website(driver, w.showings, first_element)
                ws.scrape(driver, layout, w)
            # except:
                print(f"---------- scrape failed {w.theater} ----------")
                driver = get_driver()

        json_path = Path(__file__).parent.parent.parent / "public/movies.json"
        ws.save_json(json_path)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
