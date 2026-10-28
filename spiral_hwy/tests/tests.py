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
from spiral_hwy.tools.cinema_scraper import (
    CinemaScraper,
    MovieShowing,
    get_driver,
    go_to_website,
)
from spiral_hwy.tools.landmark_scraper import LandmarkScraper
from spiral_hwy.tools.music_scraper import (
    MusicEvent,
    _normalize_age,
    _parse_12h_time,
    _split_lineup,
    dedupe,
    drop_past,
    group_by_date,
    infer_date,
)
from spiral_hwy.tools.music_venues import (
    BottomOfTheHillScraper,
    BrickAndMortarScraper,
    CafeDuNordScraper,
    ChapelScraper,
    FoxOaklandScraper,
    GreatAmericanMusicHallScraper,
    GreekTheatreScraper,
    IndependentScraper,
    RickshawStopScraper,
    _unwrap_link,
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
    ws = CinemaScraper(
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
    ws = CinemaScraper()

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

        # Now Playing section is found via the .adc-listing_movies wrapper
        section = AlamoScraper._find_now_playing_section(driver)
        assert section is not None

        cards = section.find_elements(By.CLASS_NAME, "adc-show-card")
        slugs = [AlamoScraper._card_slug(c) for c in cards]
        assert slugs == [
            "project-hail-mary",  # from the title link
            "twin-peaks-marathon",  # from the /event/ link
            "undertone",  # image-only card, from the poster URL
            "",  # unrelated image, no slug
        ]

        # A page with no Now Playing section must report it as missing
        driver.get("file:///" + str(fixtures / "show_page.html"))
        assert AlamoScraper._find_now_playing_section(driver) is None

    finally:
        driver.quit()


def test_landmark():
    """
    Test Landmark scraper: date parsing, time parsing, theater selection,
    movie extraction, and showtime detection from fixture HTML.
    """
    pacific_tz = pytz.timezone("US/Pacific")
    today = pacific_tz.localize(datetime(2026, 4, 1))

    # ------------------------------------------------------------------
    # _parse_date
    # ------------------------------------------------------------------
    parse = LandmarkScraper._parse_date

    # "Today" / "Tomorrow"
    assert parse("Today", today) == "2026-04-01"
    assert parse("Tomorrow", today) == "2026-04-02"

    # "m/d" patterns
    assert parse("4/1", today) == "2026-04-01"
    assert parse("4/2", today) == "2026-04-02"
    assert parse("12/25", today) == "2026-12-25"

    # With day name prefix
    assert parse("Wed 4/2", today) == "2026-04-02"
    assert parse("Today 4/1", today) == "2026-04-01"

    # Past dates roll to next year
    assert parse("3/1", today) == "2027-03-01"

    # "Mon DD" pattern (e.g., "Apr 3")
    assert parse("Apr 3", today) == "2026-04-03"
    assert parse("Thu Apr 3", today) == "2026-04-03"

    # "DayAbbrev DD" pattern (e.g., "Sat 4" or "Sat4") — bare day number
    # Must match both day-of-month AND weekday (2026-04-01 is a Wednesday)
    assert parse("Wed 1", today) == "2026-04-01"
    assert parse("Thu 2", today) == "2026-04-02"
    assert parse("Fri 3", today) == "2026-04-03"
    assert parse("Sat4", today) == "2026-04-04"
    assert parse("Sun5", today) == "2026-04-05"
    # "Mon1" can't be Apr 1 (Wed) — next Mon the 1st is Jun 1
    assert parse("Mon1", today) == "2026-06-01"
    # Weekday mismatch: "Sat9" on Apr 9 (Thu) → next Sat the 9th is May 9
    thu_apr_9 = pacific_tz.localize(datetime(2026, 4, 9))
    assert parse("Sat9", thu_apr_9) == "2026-05-09"
    assert parse("Thu9", thu_apr_9) == "2026-04-09"

    # Invalid inputs
    assert parse("", today) is None
    assert parse("nonsense", today) is None

    # ------------------------------------------------------------------
    # _parse_12h_time
    # ------------------------------------------------------------------
    parse_t = LandmarkScraper._parse_12h_time

    assert parse_t("1:30 PM") == "1330"
    assert parse_t("7:00 PM") == "1900"
    assert parse_t("9:30pm") == "2130"
    assert parse_t("12:00 AM") == "0000"
    assert parse_t("invalid") is None

    # ------------------------------------------------------------------
    # Selenium fixture tests
    # ------------------------------------------------------------------
    driver = get_driver()
    try:
        fixtures = Path(__file__).parent / "websites" / "landmark_opera_plaza"
        driver.get("file:///" + str(fixtures / "showtimes.html"))

        # _get_date_buttons: should find the 3 date buttons
        date_buttons = LandmarkScraper._get_date_buttons(driver)
        date_strs = [d for d, _btn in date_buttons]
        assert len(date_strs) == 3
        assert date_strs == ["Today 4/1", "Wed 4/2", "Thu 4/3"]

        # Parsed dates should be valid
        parsed = [parse(d, today) for d in date_strs]
        assert parsed == ["2026-04-01", "2026-04-02", "2026-04-03"]

        # _get_movies: should find 2 movies (the third has no showtimes)
        movies = LandmarkScraper._get_movies(driver)
        assert len(movies) == 2

        # First movie: The Brutalist
        title, rating, poster_src, showtimes = movies[0]
        assert title == "The Brutalist"
        assert rating == "R"
        assert len(showtimes) == 2
        assert showtimes[0][0] == "1:30 PM"  # time_str
        assert showtimes[0][2] is False  # not sold out
        assert showtimes[1][0] == "7:00 PM"

        # Second movie: Anora
        title, rating, poster_src, showtimes = movies[1]
        assert title == "Anora"
        assert rating == "R"
        assert len(showtimes) == 2
        assert showtimes[0][0] == "4:15 PM"
        assert showtimes[0][2] is False
        assert showtimes[1][0] == "9:30 PM"
        assert showtimes[1][2] is True  # sold out

    finally:
        driver.quit()


def test_bottom_of_the_hill():
    """
    Test Bottom of the Hill calendar parsing against a saved copy of
    https://www.bottomofthehill.com/calendar.html (fetched 2026-10-27).
    """
    assert _parse_12h_time("7:00PM") == "1900"
    assert _parse_12h_time("12:30am") == "0030"
    assert _parse_12h_time("13:00PM") is None
    assert _parse_12h_time("7 PM") == "1900"
    assert _normalize_age("\u2022\u2022\u2022 21 AND OVER") == "21+"
    assert _normalize_age("\u2022\u2022\u2022\xa0 ALL AGES") == "All Ages"
    assert _normalize_age("all-ages") == "All Ages"
    assert _normalize_age("21+") == "21+"

    fixture = (
        Path(__file__).parent / "websites" / "bottom_of_the_hill" / "calendar.html"
    )
    events = BottomOfTheHillScraper.parse(fixture.read_text(encoding="iso-8859-1"))
    by_date = {e.date: e for e in events}

    # 50 shows listed; 11/1 and 11/3 are CLOSED (cancelled) and dropped
    assert len(events) == 48
    assert "2026-11-01" not in by_date and "2026-11-03" not in by_date
    assert len({e.id for e in events}) == len(events)

    # Typical show: doors/show times, tagline, lineup with genres, links
    e = by_date["2026-10-28"]
    assert e.id == "bottom_of_the_hill-20261028-2000"
    assert (e.doors, e.time) == ("1900", "2000")
    assert e.title == "Slothrust"
    assert e.tagline == "The Dystopian Theatre Tour"
    assert [(a.name, a.genre) for a in e.artists] == [
        ("Slothrust", "rock, grunge, garage"),
        ("Um, Jennifer?", "pop rock punk"),
    ]
    assert e.age == "All Ages"
    assert e.price == "$25 in advance / $28 at the door"
    assert (
        e.ticket_link == "https://www.bottomofthehill.com/stubmatic/event20261028.html"
    )
    assert e.link == "https://www.bottomofthehill.com/20261028.html"
    assert e.image == "https://www.bottomofthehill.com/f/20261027and28fs.jpg"
    assert not e.sold_out

    # Date comes from the text, not the (stale) "20261212" anchor
    assert by_date["2026-12-13"].title == "El Vez & the Centuries"
    assert by_date["2026-12-12"].title == "Hot Lunch"

    # Sold out: no ticket button; DJ "/ Name" prefix stripped
    e = by_date["2026-11-13"]
    assert e.sold_out and e.ticket_link == ""
    assert [a.name for a in e.artists][-1] == "Mike Gabriel"
    assert sum(e.sold_out for e in events) == 13

    # "TBA" placeholders and "... and more" aren't artists
    assert [a.name for a in by_date["2026-12-01"].artists] == ["Fat, Evil Children"]
    assert "... and more" not in [a.name for a in by_date["2026-12-26"].artists]

    # Bracketed notes are dropped from the price
    assert by_date["2026-11-12"].price == "$17 in advance / $20 at the door"

    # Grouped by date, sorted by start time within a date
    grouped = group_by_date(
        [
            MusicEvent("b", "v", "", "", "", "", "2026-01-02", "2000", "B"),
            MusicEvent("c", "v", "", "", "", "", "2026-01-01", "2100", "C"),
            MusicEvent("a", "v", "", "", "", "", "2026-01-01", "1900", "A"),
        ]
    )
    assert [(d["date"], [e.id for e in d["events"]]) for d in grouped] == [
        ("2026-01-01", ["a", "c"]),
        ("2026-01-02", ["b"]),
    ]


def test_music_helpers():
    """
    Test shared music helpers: year inference, lineup splitting, dedupe.
    """
    today = datetime(2026, 10, 27).date()
    assert infer_date(10, 28, today) == "2026-10-28"
    assert infer_date(10, 26, today) == "2026-10-26"  # yesterday still counts
    assert infer_date(10, 25, today) == "2027-10-25"
    assert infer_date(1, 15, today) == "2027-01-15"
    assert infer_date(2, 29, today) == "2028-02-29" or infer_date(2, 29, today) is None
    assert infer_date(13, 1, today) is None

    assert _split_lineup("with Houses of Heaven, False Figure, a.cold.era") == [
        "Houses of Heaven",
        "False Figure",
        "a.cold.era",
    ]
    assert _split_lineup("") == []

    a = MusicEvent("x", "v", "", "", "", "", "2026-01-01", "2000", "A")
    b = MusicEvent("x", "v", "", "", "", "", "2026-01-01", "2000", "B")
    assert [e.title for e in dedupe([a, b])] == ["A"]

    # Shows before yesterday are dropped; yesterday stays (late-night shows)
    old = MusicEvent("o", "v", "", "", "", "", "2026-10-25", "2000", "Old")
    late = MusicEvent("y", "v", "", "", "", "", "2026-10-26", "2300", "Late")
    assert [e.title for e in drop_past([old, late, a], today)] == ["Late"]

    assert _normalize_age("Ages 18 and up") == "18+"


def test_the_independent():
    """
    Test The Independent (TicketWeb plugin) parsing against a saved copy of
    https://www.theindependentsf.com/ (fetched 2026-10-27; dates have no year).
    """
    fixture = Path(__file__).parent / "websites" / "the_independent" / "home.html"
    events = IndependentScraper.parse(
        fixture.read_text(encoding="utf-8"), today=datetime(2026, 10, 27).date()
    )
    by_title = {e.title: e for e in events}

    # 98 listed: 2 postponed, 1 moved to the Castro, 1 two-day pass dropped
    assert len(events) == 94
    assert len({e.id for e in events}) == len(events)
    assert not any("POSTPONED" in e.title or "MOVED" in e.title for e in events)
    assert "Two Gallants: Two-Day Pass" not in by_title

    e = by_title["Freak Slug"]
    assert e.id == "the_independent-20261028-2000"
    assert e.tagline == "AMULET TOUR NA"
    assert [a.name for a in e.artists] == ["Freak Slug", "Mamalarky"]
    assert e.link == "https://www.theindependentsf.com/tm-event/freak-slug/"
    assert e.ticket_link.startswith("https://www.ticketweb.com/event/freak-slug-")
    assert e.image.startswith("https://i.ticketweb.com/")

    # Multiple support acts, one per <span>
    assert [a.name for a in by_title["The Wldlfe"].artists] == [
        "The Wldlfe",
        "Landon Conrath",
        "brendon b",
    ]

    # Year rolls over for early-2027 dates (a two-night run)
    assert [e.date for e in events if e.title == "Two Gallants"] == [
        "2027-02-10",
        "2027-02-11",
    ]

    # Sold out via the button class ("Sold Out!") or its text ("SOLD OUT")
    assert sum(e.sold_out for e in events) == 5

    # TicketWeb's placeholder image isn't used as a flyer
    assert by_title["Thievery Corporation"].image == ""


def test_great_american_music_hall():
    """
    Test Great American Music Hall (SeeTickets month grids) parsing against a
    saved copy of https://gamh.com/calendar/ (fetched 2026-10-27).
    """
    fixture = (
        Path(__file__).parent
        / "websites"
        / "great_american_music_hall"
        / "calendar.html"
    )
    events = GreatAmericanMusicHallScraper.parse(fixture.read_text(encoding="utf-8"))
    by_title = {e.title: e for e in events}

    # 66 listed, minus a 3-show pass, a 2-day pass, two "*CANCELLED*" shows,
    # and four "PRIVATE EVENT" holds
    assert len(events) == 58
    assert not any("CANCELLED" in e.title for e in events)
    assert not any("PRIVATE" in e.title for e in events)
    assert len({e.id for e in events}) == len(events)
    assert not any("pass" in e.title.lower() for e in events)

    e = by_title["Cold Cave (solo), SRSQ"]
    assert e.date == "2026-10-30"
    assert (e.doors, e.time) == ("1800", "1830")
    assert [a.name for a in e.artists] == [
        "Cold Cave (solo), SRSQ",
        "Houses of Heaven",
        "False Figure",
        "a.cold.era",
    ]
    assert e.ticket_link.startswith("https://wl.seetickets.us/event/cold-cave-")

    # Date comes from the month heading + day cell, across the year boundary
    assert [e.date for e in events if e.title == "The 16th Annual Bowie Bash!"] == [
        "2027-01-15",
        "2027-01-16",
    ]
    assert max(e.date for e in events) == "2027-05-21"

    # Only "Sold Out" buttons count; "More Info" buttons with the sold-out
    # style are shows ticketed elsewhere (Eventbrite, TicketWeb) or holds
    assert sum(e.sold_out for e in events) == 0
    assert not by_title["A John Waters Xmas"].sold_out


def test_cafe_du_nord():
    """
    Test Cafe du Nord parsing against a saved copy of
    https://cafedunord.com/shows (fetched 2026-10-27).
    """
    fixture = Path(__file__).parent / "websites" / "cafe_du_nord" / "shows.html"
    events = CafeDuNordScraper.parse(fixture.read_text(encoding="utf-8"))
    by_title = {e.title: e for e in events}

    assert len(events) == 47
    assert len({e.id for e in events}) == len(events)

    # Upstairs shows are listed under Swedish American Hall
    assert sum(e.venue == "cafe_du_nord" for e in events) == 39
    assert sum(e.venue == "swedish_american_hall" for e in events) == 8

    e = by_title["Francis of Delirium"]
    assert e.id == "cafe_du_nord-20261029-2000"
    assert e.doors == "1900"
    assert e.age == "All Ages"
    assert [a.name for a in e.artists] == ["Francis of Delirium", "swell foop"]
    assert e.link == "https://cafedunord.com/shows/2026-10-29-francis-of-delirium"
    # the main ticket, not the "Preferred Viewing" add-on
    assert "preferred-viewing" not in e.ticket_link
    assert e.ticket_link.startswith("https://www.ticketweb.com/event/francis-of-")

    # Each .act is one artist, trailing commas stripped
    assert [a.name for a in by_title["Sobs"].artists] == ["Sobs", "Lace"]
    assert any(
        [a.name for a in e.artists][1:] == ["Clark D", "Delivery Boys"] for e in events
    )

    # "waitlist" status means sold out
    assert sum(e.sold_out for e in events) == 2


def websites(*parts: str) -> str:
    """Read a saved venue page from tests/websites/."""
    return (
        (Path(__file__).parent / "websites")
        .joinpath(*parts)
        .read_text(encoding="utf-8")
    )


def test_brick_and_mortar():
    """
    Test Brick & Mortar Music Hall (TicketWeb plugin, paginated) against its
    three pages, saved 2026-10-27.
    """
    pages = [
        websites("brick_and_mortar_music_hall", f"page{n}.html") for n in (1, 2, 3)
    ]
    # pagination: each page links to the next; the last links nowhere
    assert [BrickAndMortarScraper.next_page(p) for p in pages] == [
        "https://www.brickandmortarmusic.com/page/2/",
        "https://www.brickandmortarmusic.com/page/3/",
        None,
    ]
    today = datetime(2026, 10, 27).date()
    events = [e for p in pages for e in BrickAndMortarScraper.parse(p, today=today)]
    by_title = {e.title: e for e in events}

    assert len(events) == 45  # 21 + 21 + 3
    assert len({e.id for e in events}) == len(events)
    assert max(e.date for e in events) == "2027-05-14"  # page 3, next year

    # This theme lists openers in the name: "Hayden Everett, Jackson Lundy"
    e = by_title["Hayden Everett"]
    assert [a.name for a in e.artists] == ["Hayden Everett", "Jackson Lundy"]
    assert (e.doors, e.time) == ("1900", "2000")
    assert e.age == "All Ages"
    assert e.price == "$33.74"
    assert e.tagline == "Brick & Mortar Music Hall Presents"

    assert {e.age for e in events} == {"All Ages", "18+", "21+"}
    assert sum(e.sold_out for e in events) == 6


def test_the_chapel():
    """
    Test The Chapel (SeeTickets calendar) against a saved copy of
    https://thechapelsf.com/calendar/ (2026-10-27). The calendar holds the
    same 45 ticketed shows as the 5-page list at /music/.
    """
    events = ChapelScraper.parse(websites("the_chapel", "calendar.html"))
    by_title = {e.title: e for e in events}

    # 48 listed, minus "POSTPONED: ChapelMania" and three "Private Event" holds
    assert len(events) == 44
    assert len({e.id for e in events}) == len(events)
    assert not any("POSTPONED" in e.title for e in events)

    # "Show at" / "Doors at" times and "Supporting Talent:" openers
    e = by_title["Katie Pruitt"]
    assert (e.date, e.doors, e.time) == ("2026-10-29", "1900", "2000")
    assert [a.name for a in e.artists] == ["Katie Pruitt", "Olivia Barton"]
    assert e.ticket_link.startswith("https://wl.seetickets.us/event/katie-pruitt/")

    assert sum(e.sold_out for e in events) == 2


def test_rickshaw_stop():
    """
    Test Rickshaw Stop against a saved WordPress API response for its calendar
    page (2026-10-27); the site's HTML pages are blocked by Cloudflare.
    """
    assert (
        _unwrap_link(
            "https://urldefense.com/v3/__https://wl.eventim.us/event/x/1?afflky=A__;!!AEl5"
        )
        == "https://wl.eventim.us/event/x/1?afflky=A"
    )
    assert (
        _unwrap_link("https://wl.seetickets.us/e/1") == "https://wl.seetickets.us/e/1"
    )

    events = RickshawStopScraper.parse_api(
        websites("rickshaw_stop", "calendar_api.json")
    )
    by_title = {e.title: e for e in events}

    # 48 listed, minus one marked "Event passed"
    assert len(events) == 47
    assert len({e.id for e in events}) == len(events)
    assert not any("urldefense" in e.ticket_link for e in events)

    e = by_title["VIOLET GROHL"]
    assert (e.date, e.doors, e.time) == ("2026-10-27", "1900", "2000")
    assert [a.name for a in e.artists] == ["VIOLET GROHL", "Suzy Clue"]
    assert e.ticket_link == (
        "https://wl.eventim.us/event/violet-grohl/693274?afflky=POPSCENEPresents"
    )

    # Multiple openers; "support tba" / "opener tba" placeholders dropped
    assert [a.name for a in by_title["Natural Child"].artists] == [
        "Natural Child",
        "Buzzed Lightbeer",
        "Milk for the Angry",
        "Catnip",
    ]
    assert [a.name for a in by_title["RUBY HAUNT"].artists] == [
        "RUBY HAUNT",
        "vhs ghost",
    ]
    assert not any("tba" in a.name.lower() for e in events for a in e.artists)


def test_the_fox_oakland():
    """
    Test The Fox Oakland against a saved copy of
    https://thefoxoakland.com/listing/ (2026-10-27).
    """
    events = FoxOaklandScraper.parse(websites("the_fox_oakland", "listing.html"))
    by_title = {e.title: e for e in events}

    assert len(events) == 35
    assert len({e.id for e in events}) == len(events)

    e = by_title["Jessie Reyez"]
    assert (e.date, e.doors, e.time) == ("2026-11-06", "1900", "2000")
    assert e.tagline == "A Little Vengeance Tour 2026"
    assert e.sold_out
    assert e.ticket_link.startswith("https://www.ticketmaster.com/jessie-reyez-")
    assert e.link == "https://thefoxoakland.com/events/jessie-reyez-261106"

    # Multi-night runs are separate events
    assert [e.date for e in events if e.title == "Pretty Lights"] == [
        "2026-11-19",
        "2026-11-20",
        "2026-11-21",
    ]
    assert sum(e.sold_out for e in events) == 6


def test_the_greek_theatre():
    """
    Test The Greek Theatre against a saved copy of its home page (2026-10-27),
    which lists every upcoming show (it matches /calendar).
    """
    events = GreekTheatreScraper.parse(websites("the_greek_theatre", "home.html"))
    assert [(e.date, e.title) for e in events] == [
        (
            "2026-11-04",
            "Ms. Lauryn Hill & Wyclef Jean: Celebrating 30 years of Fugees’ The Score",
        ),
        ("2026-11-07", "HUGEL"),
        ("2027-08-12", "The Red Clay Strays"),
        ("2027-09-07", "Sienna Spiro"),
    ]
    assert events[0].doors == "1730" and events[0].time == "1900"
    assert all(e.venue == "the_greek_theatre" for e in events)
