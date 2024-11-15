#!/usr/bin/env python3

import selenium
import hydra
from omegaconf import DictConfig, OmegaConf
import selenium.webdriver


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


def bubble(func):
    def wrapper(*args, **kwargs):
        if kwargs.get("can_fail"):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # print(!!!!!!!!!!!!"")
                # print(f"Caught error in {func.__name__}: {str(e)}")
                return None  # Return None instead of silently failing
        else:
            return func(*args, **kwargs)
    return wrapper




def click(item):
    item.click()

actions = {
    "click" : click
}

func = {
    "id" : By.ID,
    "class": By.CLASS_NAME,
    "selector": By.CSS_SELECTOR,
    "tag": By.TAG_NAME
}

# @bubble
def get_attr(item, asset):
   return item.get_attribute(asset.field)

# @bubble
def text_member(item, asset):
   return item.text

asset_getter = {
    "get_attribute" : get_attr,
    "text_member" : text_member
}

@bubble
def unpack_item(root, type, element: DictConfig, multiple, **kwargs):
    print()
    print(element.field)
    print(element.by)     
    print(element.get("can_fail"))
    print(kwargs.get("can_fail"))

    if multiple:
        items = root.find_elements(type, element.field)
        print("items:", len(items))
        for i, item in enumerate(items):
            print(f"FIELD {i}/{len(items)}:", element.field)
            print("---1")
            unpack(item, element.child)
            print("---2")
    else:
        # try:
        item = root.find_element(type, element.field)
        if element.get("action"):
            for a in element.action:
                actions[a](item)
        if element.get("asset"):
            a = element.asset
            # try:
            print(a.name, asset_getter[a.method](item, a))
            # except:
            #     pass

        # except:
        #     pass
        #     # if kwargs.get("can_fail"):

        #     #     pass
        #     # else:
        #     #     raise Exception

@bubble
def unpack(root, config: DictConfig):
    print(config)
    for c in config:
        print("--3")
        unpack_item(
            root,
            func[c.by],
            c,
            c.get("multiple", False),
            can_fail = c.get("can_fail", False)
        )
        print("--4")

        


@hydra.main(version_base=None, config_path="configs", config_name="main")
def main(config: DictConfig):

    try:


        # Replace with your actual URL
        driver.get(movie_site)
        
        # Wait for the content to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "date"))
        )
        
        unpack(driver, config.four_star.dates_list)

        # # Get and print movie information
        # movies = get_movie_information(driver)
        # # print_movie_schedule(movies)
        
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
