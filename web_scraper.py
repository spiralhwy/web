#!/usr/bin/env python3

import selenium
import hydra
from omegaconf import DictConfig, OmegaConf
import selenium.webdriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.common.exceptions import NoSuchElementException

# from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from webdriver_manager.chrome import ChromeDriverManager

# Set up Chrome options
#chrome_options = Options()
# chrome_options.add_argument('--headless')  # Run in headless mode (no GUI)
#chrome_options.add_argument('--disable-notifications')  # Disable notifications

# Initialize the driver
#driver = webdriver.Chrome(
        #  service=Service(ChromeDriverManager().install()),
        # options=chrome_options
    #)

# Navigate to a website
movie_site = "https://ticketing.uswest.veezi.com/sessions/?siteToken=d2atbcege5knqsavntt91g1250"
#driver.get(site)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


from selenium.webdriver.chrome.options import Options
ops = Options()
ops.add_argument("--headless=new")
driver = webdriver.Chrome(options=ops)  # Make sure to have ChromeDriver installed

@dataclass
class MovieSession:
    time: str
    link: str
    status: str

@dataclass
class MovieInfo:
    title: str
    rating: Optional[str]
    date: str
    sessions: List[MovieSession]





def get_movie_information(driver: webdriver.Chrome) -> List[MovieInfo]:
    """
    Extracts movie information from the webpage organized by date
    """
    sort = driver.find_element(By.ID, "byDateTab")
    sort.click()

    movies = []
    
    # Find all date sections
    date_sections = driver.find_elements(By.CLASS_NAME, "date")
    print("date sections len: ", len(date_sections))
    for date_section in date_sections:

        try:
            date = date_section.find_element(
                By.CSS_SELECTOR, "h3.date-title.highlight-foreground").get_attribute("innerHTML")        #date_title = date_section.find_element(By.XPATH, ".//h3[@class='date-title highlight-foreground']")  # Use XPath to find the h3
        except:
            print("passss")
            pass
            
        movie_elements = date_section.find_elements(By.CLASS_NAME, "film ")
        # print(len(movie_elements))
        
        for movie in movie_elements:
            try:
                # Extract movie title
                title = movie.find_element(By.CSS_SELECTOR, "h3.title").get_attribute("innerHTML")
                print(title.strip())
                # Extract rating if available
                try:
                    rating = movie.find_element(By.CLASS_NAME, "censor").text
                    print("rating:", rating)
                except:
                    rating = None
                
                # Extract sessions
                sessions = []
                session_elements = movie.find_elements(By.CSS_SELECTOR, ".session-times li")
                
                for session in session_elements:
                    time = session.find_element(By.TAG_NAME, "time").text
                    print("time:", time)

                    link = session.find_element(By.TAG_NAME, "a").get_attribute("href")
                    print("link:", link)
                    
                    # Check if session is sold out
                    try:
                        status = session.find_element(By.CLASS_NAME, "tickets-sold-out").text
                    except:
                        status = "Available"
                    
                    sessions.append(MovieSession(time=time, status=status, link=link))
                
                movies.append(MovieInfo(
                    title=title,
                    rating=rating,
                    date=date,
                    sessions=sessions
                ))
                
            except Exception as e:
                print(f"Error processing movie: {e}")
                continue
    
    return movies

def print_movie_schedule(movies: List[MovieInfo]):
    """
    Prints the movie schedule in a readable format
    """
    current_date = None
    
    for movie in movies:
        # Print date header if it's a new date
        if movie.date != current_date:
            print(f"\n=== {movie.date} ===")
            current_date = movie.date
        
        # Print movie information
        print(f"\n{movie.title}")
        if movie.rating:
            print(f"Rating: {movie.rating}")
        
        print("Sessions:")
        for session in movie.sessions:
            print(f"  {session.time} - {session.status}")








def catch_optional(func):
    def wrapper(*args, **kwargs):
        if kwargs.get("optional"):
            try:
                return func(*args, **kwargs)
            except NoSuchElementException:
                print("----- Optional element -----")
                return None
        else:
            return func(*args, **kwargs)
    return wrapper



ATTRIBUTE_ID = {
    "id" : By.ID,
    "class_name": By.CLASS_NAME,
    "css_selector": By.CSS_SELECTOR,
    "tag_name": By.TAG_NAME
}

def element_click(item: WebElement) -> None:
    item.click()

ELEMENT_ACTIONS = {
    "click" : element_click
}


def get_element_attribute(element: WebElement, asset: DictConfig) -> str:
   return element.get_attribute(asset.field)

def get_element_text(item: WebElement, _asset: DictConfig) -> str:
   return item.text

ASSET_GETTER = {
    "get_attribute" : get_element_attribute,
    "text_member" : get_element_text
}

@catch_optional
def unpack_element(root: WebDriver | WebElement, attribute_id, config: DictConfig, **kwargs) -> None:
    """
    Unpack single element.
    """
    if config.get("child"):
        elements = root.find_elements(attribute_id, config.field)
        for e in elements:
            unpack_list(e, config.child)

    else:
        element = root.find_element(attribute_id, config.field)
        if config.get("action"):
            for a in config.action:
                ELEMENT_ACTIONS[a](element)

        if config.get("asset"):
            # this should assign assets
            a = config.asset
            print(a.name, ASSET_GETTER[a.method](element, a))

@catch_optional
def unpack_list(root: WebDriver | WebElement, config: DictConfig) -> None:
    """
    Unpack config list.
    """
    for c in config:
        unpack_element(
            root,
            ATTRIBUTE_ID[c.by],
            c,
            optional = c.get("optional", False)
        )

        


@hydra.main(version_base=None, config_path="configs", config_name="main")
def main(config: DictConfig):

    try:

        dates_list: DictConfig = config.four_star.dates_list
        first_element: DictConfig = dates_list[0]

        # Replace with your actual URL
        driver.get(movie_site)
        
        # Wait for the content to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((
                ATTRIBUTE_ID[first_element.by], 
                first_element.field))
        )
        
        unpack_list(driver, dates_list)
        
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
