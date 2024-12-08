#!/usr/bin/env python3
"""
Web scraper to get data from movie listing website.
"""

import base64
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import hydra
import pytz
import requests
from omegaconf import DictConfig
from pytz import timezone
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sort_tools import quicksort
from webdriver_manager.chrome import ChromeDriverManager

ATTRIBUTE_ID = {
    "id": By.ID,
    "class_name": By.CLASS_NAME,
    "css_selector": By.CSS_SELECTOR,
    "tag_name": By.TAG_NAME,
}


@dataclass
class MovieShowing:
    """
    Showing event.
    """

    available: bool
    link: str
    time: str


@dataclass
class MovieListing:
    """
    Daily movie listing: location, showings, etc.
    """

    showings: List[MovieShowing]
    theater: str
    map: str
    area: str
    theater_link: str


def catch_optional(func):
    """
    Allow web element to not exist if optional flag.
    """

    def wrapper(*args, **kwargs):
        if "optional" in kwargs:
            try:
                return func(*args, **kwargs)
            except NoSuchElementException:
                return None
        else:
            return func(*args, **kwargs)

    return wrapper


def go_to_website(driver: WebDriver, website: str, first_element: DictConfig) -> None:
    """
    Go to website with Selenium web driver.
    """
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
    """
    Get Selenium web driver.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode (no GUI)
    chrome_options.add_argument("--disable-notifications")  # Disable notifications

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=chrome_options
    )

    return driver


class WebScraper:
    """
    Class to scrape movie showing info from website.
    """

    def __init__(
        self, poster_dir: Path = Path(__file__).parent.parent.parent / "public/posters"
    ):

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

        self.asset_getters = {
            "get_attribute": self._get_element_attribute,
            "text_member": self._get_element_text,
        }

        self.asset_special = {
            "convert_date": self._convert_date,
            "convert_time": self._convert_time,
        }

        self.actions = {
            "create_listing": self._create_listing,
            "create_showing": self._create_showing,
            "save_poster": self._save_poster,
            "click": self._element_click,
            "unpack": self._unpack,
            "get_asset": self._get_asset,
        }

    @staticmethod
    def _element_click(element: WebElement, _config: DictConfig) -> None:
        """
        Click web element.
        """
        element.click()

    @staticmethod
    def _get_element_attribute(element: WebElement, asset: DictConfig) -> str:
        """
        Get attribute of web element.
        Strip off any whitespace.
        """
        output = element.get_attribute(asset.field)
        if isinstance(output, str):
            return output.strip()
        return output

    @staticmethod
    def _get_element_text(item: WebElement, _asset: DictConfig) -> str:
        """
        Get text only from web element.
        """
        return item.text.strip()

    def _convert_date(self, date: str, config: DictConfig) -> str:
        """
        Convert date text to a standardized format.
        """
        # Define Pacific Time timezone
        pacific_tz = pytz.timezone("US/Pacific")

        # Get today's date in Pacific Time
        today = datetime.now(pacific_tz)
        yesterday = today - timedelta(days=1)

        # First try current year
        current_year = today.year
        date_str_with_year = f"{date} {current_year}"

        # Parse the date in the local timezone (Pacific Time)
        date_obj = datetime.strptime(date_str_with_year, config.format)

        # Localize the parsed date to Pacific Time
        date_obj = pacific_tz.localize(date_obj)

        # If the date is before yesterday in Pacific Time, add a year
        if date_obj < yesterday:
            date_obj = datetime.strptime(f"{date} {current_year + 1}", "%A %d, %B %Y")
            date_obj = pacific_tz.localize(date_obj)

        # Return the date in the standardized format (YYYY-MM-DD)
        return date_obj.strftime("%Y-%m-%d")

    def _convert_time(self, time: str, config: DictConfig) -> str:
        """
        Convert time to standardized format.
        """
        date_obj = datetime.strptime(time, config.format)
        return date_obj.strftime("%H%M")

    def _create_listing(self, _element: WebElement, _config: DictConfig) -> None:
        """
        Create movie listing. This includes location and showing times.
        """
        # there should be showings for each listing
        if len(self.showings) == 0:
            raise RuntimeError("No showings for listing")

        # clean up title
        self.assets["title"] = self.assets["title"].replace("&amp;", "&")

        # initialize dictionaries
        date_dict = self.listings.get(self.assets["date"], dict())
        title_dict: dict = date_dict.get(self.assets["title"], dict())
        if len(title_dict.keys()) == 0:
            for k in ["poster", "rating"]:
                title_dict.update({k: self.assets[k]})

        # add listing object
        listings_list = title_dict.get("listings", list())
        listings_list.append(
            MovieListing(
                self.showings.copy(),
                self.assets["theater"],
                self.assets["map"],
                self.assets["area"],
                self.assets["theater_link"],
            )
        )
        title_dict.update({"listings": listings_list})
        date_dict.update({self.assets["title"]: title_dict})
        self.listings.update({self.assets["date"]: date_dict})

        # reset assets
        self.assets["poster"] = ""
        self.assets["rating"] = ""
        self.showings.clear()
        self.assets["title"] = ""

    def _create_showing(self, _element: WebElement, _config: DictConfig) -> None:
        """
        Create showing object containing time and link to tickets.
        """
        if not self.assets["time"]:
            raise RuntimeError("No link or time information for showing.")

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

    def _execute_actions(self, element: WebElement, config: DictConfig) -> None:
        """
        Execute actions on a web element / its config item.
        """
        for c in config:
            self.actions[c.action](element, c)

    def _get_asset(self, element: WebElement, config: DictConfig) -> None:
        """
        Get asset from web element and store in class object.
        """
        self.assets[config.name] = self.asset_getters[config.method](element, config)

        if "special" in config:
            self.assets[config.name] = self.asset_special[config.special.method](
                self.assets[config.name], config.special
            )

    def _save_poster(self, element: WebElement, config: DictConfig) -> None:
        """
        Save poster image.
        """
        self._get_asset(element, config)

        self.assets[config.name] = base64.urlsafe_b64encode(
            self.assets[config.name].lower().encode()
        ).decode("utf-8")

        poster_src = element.get_attribute("src")
        save_path = self.poster_dir / f"{self.assets[config.name]}.png"
        save_path.parent.mkdir(exist_ok=True, parents=True)
        save_path = str(save_path)

        if not Path(save_path).exists():
            file_str = "file://"
            if poster_src.startswith(file_str):
                local_path = poster_src[len(file_str) :]  # Strip off "file://"
                with open(local_path, "rb") as img_file:
                    img_data = img_file.read()
            else:
                img_data = requests.get(poster_src).content

            with open(save_path, "wb") as handler:
                handler.write(img_data)

    def _sort_showings_by_times(self) -> None:
        """
        Sort listings and movies.
        Listings for each movie are sorted first.
        Then each movie is sorted for the day.
        """

        def get_showing_time(movie_listing: MovieListing):
            """
            Callback to extract first showing time.
            """
            return int(movie_listing.showings[0].time)

        def get_listing_time(movie_showing: dict):
            """
            Callback to extract first showing time from first listing.
            """
            return int(get_showing_time(movie_showing["listings"][0]))

        # sort showings
        for date, movies in self.listings.items():
            for movie_data in movies.values():
                quicksort(
                    movie_data["listings"],
                    0,
                    len(movie_data["listings"]) - 1,
                    get_showing_time,
                )

        # sort movies
        for date, movies in self.listings.items():
            movie_list = []
            for title, movie_data in movies.items():
                movie_data.update({"title": title})
                movie_list.append(movie_data)
            quicksort(movie_list, 0, len(movie_list) - 1, get_listing_time)
            self.listings.update({date: movie_list})

    def _unpack(self, element: WebElement, config: DictConfig) -> None:
        """
        Small wrapper function for a config element that wants to get its child elements.
        """
        self._unpack_list(element, config.children)

    @catch_optional
    def _unpack_element(
        self, root: WebDriver | WebElement, attribute_id, config: DictConfig, **kwargs
    ) -> None:
        """
        Unpack element type. There may be multiple elements of that type to get from the page.
        """
        elements = []
        if "multiple" in config.get("meta", []):
            elements.extend(root.find_elements(attribute_id, config.field))
        else:
            elements.append(root.find_element(attribute_id, config.field))

        if "actions" in config:
            for e in elements:
                self._execute_actions(e, config.actions)

    @catch_optional
    def _unpack_list(self, root: WebDriver | WebElement, config: DictConfig) -> None:
        """
        Unpack config list.
        """
        for c in config:
            is_optional = "optional" in c.get("meta", [])
            self._unpack_element(root, ATTRIBUTE_ID[c.by], c, optional=is_optional)

    def save_json(self, path: Path) -> None:
        """
        Save JSON file.
        """
        self._sort_showings_by_times()
        path.parent.mkdir(exist_ok=True, parents=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.listings, f, indent=4, default=lambda o: o.__dict__)

    def scrape(
        self, root: WebDriver | WebElement, config: DictConfig, website: str
    ) -> None:
        """
        Primary function to call to scrape website.
        """
        self.assets["theater"] = website.theater
        self.assets["map"] = website.map
        self.assets["area"] = website.area
        self.assets["theater_link"] = website.link
        self.showings = list()
        self._unpack_list(root, config)


@hydra.main(version_base=None, config_path="../configs", config_name="main")
def main(config: DictConfig):

    ws = WebScraper()

    layout: DictConfig = config.veezi.dates_list
    first_element = layout[0]

    try:
        driver = get_driver()
        for w in config.veezi.websites:
            try:
                print("-" * 10, f"scrape {w.theater}", "-" * 10)
                go_to_website(driver, w.showings, first_element)
                ws.scrape(driver, layout, w)
            except:
                print("-" * 10, f"scrape failed {w.theater}", "-" * 10)
                driver = get_driver()

        json_path = Path(__file__).parent.parent / "_data" / "movies.json"
        ws.save_json(json_path)  # sorts data as well

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
