"""
Per-venue scrapers for the music listings. Each one fetches a venue's
calendar page and parses it into `MusicEvent`s (see music_scraper.py).

`parse` methods take the page HTML (and, where the page omits the year, the
current date) so they can be tested against saved copies of the pages.
"""

import calendar
import re
from datetime import date, datetime
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from music_scraper import (
    Artist,
    MusicEvent,
    Venue,
    _clean,
    _normalize_age,
    _parse_12h_time,
    _split_lineup,
    fetch_html,
    infer_date,
)

MONTHS = "|".join(calendar.month_name[1:])

# Placeholder lineup entries that aren't real artists.
PLACEHOLDER_ARTISTS = {"", "tba", "tbd"}

# Listing text that means the show isn't happening at the venue as listed.
NOT_HAPPENING = re.compile(r"\b(CLOSED|CANCEL+ED|POSTPONED|MOVED)\b", re.IGNORECASE)

# Multi-day/multi-show passes are listed alongside the shows they cover
# ("Two Gallants: Two-Day Pass", "*3-Show Pass*"); they aren't separate shows.
TICKET_PASS = re.compile(
    r"\b(\d+|two|three|four)[\s-](day|show|night)\s+pass\b", re.IGNORECASE
)


def _artists(names: List[str]) -> List[Artist]:
    return [Artist(name=n) for n in names if n.lower() not in PLACEHOLDER_ARTISTS]


# ----------------------------------------------------------------------
# Bottom of the Hill
# ----------------------------------------------------------------------

BOTTOM_OF_THE_HILL = Venue(
    slug="bottom_of_the_hill",
    link="https://www.bottomofthehill.com/",
    area="potrero_hill",
    address="1233 17th St, San Francisco, CA 94107",
    map_link="https://maps.app.goo.gl/7N3FiwEQgFQ75nit5",
)


def _https(url: str) -> str:
    """Bottom of the Hill links are written as http:// but the site serves https."""
    return re.sub(r"^http://", "https://", url)


def _in_div(el: Tag, cell: Tag) -> bool:
    """Whether `el` sits inside a <div> nested within `cell`."""
    for parent in el.parents:
        if parent is cell:
            return False
        if parent.name == "div":
            return True
    return False


class BottomOfTheHillScraper:
    """
    Scrape https://www.bottomofthehill.com/calendar.html.

    The calendar is one hand-maintained static HTML table: one <tr> per show,
    with cells for the flyer, the ticket button, the details (date, times, age,
    price, lineup — marked up with class="date|time|age|cover|for|band|genre"),
    and a Facebook link.
    """

    URL = "https://www.bottomofthehill.com/calendar.html"

    @classmethod
    def scrape(cls) -> List[MusicEvent]:
        # Page is declared ISO-8859-1; requests' guess can differ.
        return cls.parse(fetch_html(cls.URL, encoding="iso-8859-1"))

    @classmethod
    def parse(cls, html: str) -> List[MusicEvent]:
        soup = BeautifulSoup(html, "html.parser")
        events = []
        for cell in soup.find_all("td"):
            # Detail cells start with an <a name="YYYYMMDD"> anchor. The anchor
            # isn't trusted for the date (it's hand-edited and sometimes stale);
            # it only identifies the cell.
            if not cell.find("a", attrs={"name": re.compile(r"^\d{8}$")}):
                continue
            try:
                event = cls._parse_event(cell)
            except ValueError as e:
                print(f"  Bottom of the Hill: skipping unparseable event: {e}")
                continue
            if event is not None:
                events.append(event)
        return events

    @staticmethod
    def _top_level(cell: Tag, class_: str) -> List[Tag]:
        """
        Elements of a class that describe the event itself. Cancelled shows
        keep their original (struck-through) details in a nested <div>; skip those.
        """
        return [el for el in cell.find_all(class_=class_) if not _in_div(el, cell)]

    @classmethod
    def _parse_event(cls, cell: Tag) -> MusicEvent | None:
        date_text = _clean(
            " ".join(el.get_text() for el in cls._top_level(cell, "date"))
        )
        m = re.search(rf"({MONTHS})\s+(\d{{1,2}})\s+(\d{{4}})", date_text)
        if not m:
            raise ValueError(f"no date in {date_text!r}")
        month = list(calendar.month_name).index(m.group(1))
        date = f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"

        time_text = _clean(
            "".join(el.get_text() for el in cls._top_level(cell, "time"))
        )
        if NOT_HAPPENING.search(time_text):
            print(f"  Bottom of the Hill: {date} is closed/cancelled, skipping")
            return None
        times = [
            _parse_12h_time(t)
            for t in re.findall(r"\d{1,2}:\d{2}\s*[AP]M", time_text, re.IGNORECASE)
        ]
        times = [t for t in times if t]
        if not times:
            raise ValueError(f"{date}: no time in {time_text!r}")
        # "7:00PM doors -- music at 8:00PM"
        doors, start = (times[0], times[1]) if len(times) > 1 else ("", times[0])

        artists = cls._parse_artists(cell)
        taglines = [
            t
            for t in (_clean(el.get_text()) for el in cls._top_level(cell, "for"))
            if t.strip("-")
        ]
        title = artists[0].name if artists else (taglines[0] if taglines else "")
        if not title:
            raise ValueError(f"{date}: no lineup")

        age = _normalize_age(
            " ".join(el.get_text() for el in cls._top_level(cell, "age"))
        )
        price = _clean("".join(el.get_text() for el in cls._top_level(cell, "cover")))
        price = _clean(re.sub(r"\[[^\]]*\]", "", price))  # e.g. "[co-headlining]"

        row = cell.find_parent("tr")
        ticket_link = link = image = ""
        sold_out = row.find("img", alt="SOLD OUT") is not None
        for a in row.find_all("a", href=True):
            href = a["href"]
            img = a.find("img")
            if img is not None and img.get("alt") == "BUY TICKETS ONLINE":
                ticket_link = ticket_link or _https(href)
            elif re.search(r"/\d{8}\.html$", href):
                link = link or _https(href)
            elif re.search(r"/f/[^/]+f\.jpg$", href) and img is not None:
                # small thumbnail ("...fs.jpg") of the full flyer
                image = image or _https(img.get("src", ""))

        return BOTTOM_OF_THE_HILL.event(
            date,
            start,
            title,
            doors=doors,
            tagline=taglines[0] if artists and taglines else "",
            artists=artists,
            age=age,
            price=price,
            ticket_link=ticket_link,
            link=link or cls.URL,
            image=image,
            sold_out=sold_out,
        )

    @classmethod
    def _parse_artists(cls, cell: Tag) -> List[Artist]:
        """
        Lineup in billing order. Each class="band" may be followed by a
        class="genre"; DJs between sets are written as "/ Name".
        """
        artists: List[Artist] = []
        current: Artist | None = None
        for el in cell.find_all(class_=["band", "genre"]):
            if _in_div(el, cell):
                continue
            text = _clean(el.get_text())
            if "band" in el["class"]:
                name = text.lstrip("/ ").strip()
                if name.lower() in PLACEHOLDER_ARTISTS or name.startswith("..."):
                    current = None
                    continue
                current = Artist(name=name)
                artists.append(current)
            elif current is not None and not current.genre:
                current.genre = text
        return artists


# ----------------------------------------------------------------------
# The Independent
# ----------------------------------------------------------------------

THE_INDEPENDENT = Venue(
    slug="the_independent",
    link="https://www.theindependentsf.com/",
    area="western_addition",
    address="628 Divisadero St, San Francisco, CA 94117",
    map_link="https://maps.app.goo.gl/XdbVBeLgAVTwJkD99",
)


class IndependentScraper:
    """
    Scrape https://www.theindependentsf.com/.

    The home page lists every upcoming show via TicketWeb's "event discovery"
    WordPress plugin: one .tw-event-item per show, with the date as "M.D"
    (no year), a "Show: 8:00 PM" time, and the status in the ticket button
    ("Buy Tickets", "Sold Out!", "POSTPONED", "SHOW MOVED TO CASTRO", ...).
    """

    URL = "https://www.theindependentsf.com/"

    @classmethod
    def scrape(cls) -> List[MusicEvent]:
        return cls.parse(fetch_html(cls.URL))

    @classmethod
    def parse(cls, html: str, today: date | None = None) -> List[MusicEvent]:
        soup = BeautifulSoup(html, "html.parser")
        events = []
        for item in soup.select(".tw-event-item"):
            try:
                event = cls._parse_event(item, today)
            except ValueError as e:
                print(f"  The Independent: skipping unparseable event: {e}")
                continue
            if event is not None:
                events.append(event)
        return events

    @staticmethod
    def _text(item: Tag, selector: str) -> str:
        el = item.select_one(selector)
        return _clean(el.get_text(" ")) if el else ""

    @classmethod
    def _parse_event(cls, item: Tag, today: date | None) -> MusicEvent | None:
        title = cls._text(item, ".tw-name")
        status = cls._text(item, ".tw-buy-tix-btn")
        if NOT_HAPPENING.search(status) or NOT_HAPPENING.search(title):
            print(f"  The Independent: {title!r} is {status!r}, skipping")
            return None
        if TICKET_PASS.search(title):
            return None

        md = cls._text(item, ".tw-event-date")
        m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})", md)
        event_date = m and infer_date(int(m.group(1)), int(m.group(2)), today)
        if not event_date:
            raise ValueError(f"{title!r}: bad date {md!r}")

        time_text = cls._text(item, ".tw-event-time")
        start = _parse_12h_time(re.sub(r"^\s*Show:\s*", "", time_text))
        if not start:
            raise ValueError(f"{title!r}: bad time {time_text!r}")

        support = [
            _clean(s.get_text())
            for s in item.select(".tw-attractions span")
            if _clean(s.get_text())
        ]
        name_link = item.select_one(".tw-name a")
        ticket = item.select_one("a.tw-buy-tix-btn")
        img = item.select_one(".tw-image img")
        image = ""
        if img is not None and "default-event-img" not in (img.get("class") or []):
            image = img.get("src", "")

        buy_classes = ticket.get("class", []) if ticket else []
        return THE_INDEPENDENT.event(
            event_date,
            start,
            title,
            tagline=cls._text(item, ".tw-prefix"),
            artists=_artists([title] + support),
            ticket_link=ticket.get("href", "") if ticket else "",
            link=name_link.get("href", "") if name_link else cls.URL,
            image=image,
            sold_out="tw_soldout" in buy_classes
            or bool(re.search(r"sold\s*out", status, re.IGNORECASE)),
        )


# ----------------------------------------------------------------------
# Great American Music Hall
# ----------------------------------------------------------------------

GREAT_AMERICAN_MUSIC_HALL = Venue(
    slug="great_american_music_hall",
    link="https://gamh.com/",
    area="tenderloin",
    address="859 O'Farrell St, San Francisco, CA 94109",
)


class GreatAmericanMusicHallScraper:
    """
    Scrape https://gamh.com/calendar/.

    The page renders SeeTickets month grids: a "October 2026" heading
    (.seetickets-calendar-year-month-container) before each <table>, and each
    show as a .seetickets-calendar-event-container inside the <td> for its day
    (.date-number). Sold-out shows' buttons have class "button-soldout".
    """

    URL = "https://gamh.com/calendar/"

    @classmethod
    def scrape(cls) -> List[MusicEvent]:
        return cls.parse(fetch_html(cls.URL))

    @classmethod
    def parse(cls, html: str) -> List[MusicEvent]:
        soup = BeautifulSoup(html, "html.parser")
        events = []
        for table in soup.select("table.seetickets-calendar"):
            heading = table.find_previous(
                class_="seetickets-calendar-year-month-container"
            )
            try:
                month_start = datetime.strptime(
                    _clean(heading.get_text(" ")) if heading else "", "%B %Y"
                )
            except ValueError:
                print(f"  GAMH: skipping month with heading {heading!r}")
                continue
            for card in table.select(".seetickets-calendar-event-container"):
                try:
                    event = cls._parse_event(card, month_start)
                except ValueError as e:
                    print(f"  GAMH: skipping unparseable event: {e}")
                    continue
                if event is not None:
                    events.append(event)
        return events

    @staticmethod
    def _parse_event(card: Tag, month_start: datetime) -> MusicEvent | None:
        title_link = card.select_one(".seetickets-calendar-event-title a")
        title = _clean(title_link.get_text(" ")) if title_link else ""
        if not title:
            raise ValueError("no title")
        if TICKET_PASS.search(title):
            return None

        day = card.find_parent("td").select_one(".date-number")
        try:
            event_date = month_start.replace(day=int(day.get_text(strip=True)))
        except (AttributeError, ValueError):
            raise ValueError(f"{title!r}: no day number")

        times = {}
        for p in card.select(".seetickets-calendar-event-date p"):
            m = re.match(r"Event (Showtime|Doortime):\s*(.+)", _clean(p.get_text(" ")))
            if m:
                times[m.group(1)] = _parse_12h_time(m.group(2))
        start = times.get("Showtime") or times.get("Doortime")
        if not start:
            raise ValueError(f"{title!r}: no time")

        support = card.select_one(".supporting-talent")
        button = card.select_one(".seetickets-buy-btn")
        img = card.select_one("img.seetickets-calendar-event-picture")
        ticket_link = title_link.get("href", "")
        return GREAT_AMERICAN_MUSIC_HALL.event(
            event_date.strftime("%Y-%m-%d"),
            start,
            title,
            doors=times.get("Doortime") or "",
            artists=_artists(
                [title] + (_split_lineup(support.get_text()) if support else [])
            ),
            ticket_link=ticket_link,
            link=ticket_link,
            image=img.get("src", "") if img else "",
            sold_out=button is not None and "button-soldout" in button.get("class", []),
        )


# ----------------------------------------------------------------------
# Cafe du Nord / Swedish American Hall
# ----------------------------------------------------------------------

CAFE_DU_NORD = Venue(
    slug="cafe_du_nord",
    link="https://cafedunord.com/",
    area="castro",
    address="2170 Market St, San Francisco, CA 94114",
    map_link="https://maps.app.goo.gl/39WYLg6EuhLTs2a66",
)

# Upstairs, same building and calendar; listed as its own venue.
SWEDISH_AMERICAN_HALL = Venue(
    slug="swedish_american_hall",
    link="https://cafedunord.com/",
    area="castro",
    address="2174 Market St, San Francisco, CA 94114",
    map_link="https://maps.app.goo.gl/2YfxU6CWYVRycAns9",
)


class CafeDuNordScraper:
    """
    Scrape https://cafedunord.com/shows.

    One <li class="show-row"> per show with data-room ("cdn" downstairs,
    "sah" for Swedish American Hall upstairs), data-status ("on-sale",
    "presale", "waitlist" = sold out) and data-age, plus ISO <time datetime>
    stamps for doors and show.
    """

    URL = "https://cafedunord.com/shows"
    ROOMS = {"cdn": CAFE_DU_NORD, "sah": SWEDISH_AMERICAN_HALL}

    @classmethod
    def scrape(cls) -> List[MusicEvent]:
        return cls.parse(fetch_html(cls.URL))

    @classmethod
    def parse(cls, html: str) -> List[MusicEvent]:
        soup = BeautifulSoup(html, "html.parser")
        events = []
        for row in soup.select("li.show-row"):
            try:
                event = cls._parse_event(row)
            except ValueError as e:
                print(f"  Cafe du Nord: skipping unparseable event: {e}")
                continue
            if event is not None:
                events.append(event)
        return events

    @staticmethod
    def _local_time(row: Tag, selector: str) -> datetime | None:
        """Parse a <time datetime="2026-10-29T20:00:00-07:00"> (already local)."""
        el = row.select_one(selector)
        if el is None or not el.get("datetime"):
            return None
        return datetime.fromisoformat(el["datetime"])

    @classmethod
    def _parse_event(cls, row: Tag) -> MusicEvent | None:
        headliner = row.select_one(".show-row__headliner a")
        title = _clean(headliner.get_text(" ")) if headliner else ""
        if not title:
            raise ValueError("no headliner")

        status = row.get("data-status", "")
        if NOT_HAPPENING.search(status.replace("-", " ")):
            print(f"  Cafe du Nord: {title!r} is {status!r}, skipping")
            return None
        if TICKET_PASS.search(title):
            return None

        venue = cls.ROOMS.get(row.get("data-room", ""))
        if venue is None:
            raise ValueError(f"{title!r}: unknown room {row.get('data-room')!r}")

        show = cls._local_time(row, ".show-times__show time") or cls._local_time(
            row, ".show-row__date time"
        )
        if show is None:
            raise ValueError(f"{title!r}: no show time")
        doors = cls._local_time(row, ".show-times__doors time")

        # each .act is one artist: "with Clark D," / "Delivery Boys"
        support = [
            re.sub(r"^with\s+", "", _clean(a.get_text(" "))).rstrip(",").strip()
            for a in row.select(".show-row__support .act")
        ]
        ticket = row.select_one("a[data-action='buy']") or row.select_one(
            "a.show-row__btn"
        )
        img = row.select_one(".show-row__media img")
        return venue.event(
            show.strftime("%Y-%m-%d"),
            show.strftime("%H%M"),
            title,
            doors=doors.strftime("%H%M") if doors else "",
            artists=_artists([title] + support),
            age=_normalize_age(row.get("data-age", "")),
            ticket_link=ticket.get("href", "") if ticket else "",
            link=urljoin(cls.URL, headliner.get("href", "")),
            image=img.get("src", "") if img else "",
            sold_out=status in ("waitlist", "sold-out"),
        )


SCRAPERS = [
    ("bottom_of_the_hill", BottomOfTheHillScraper.scrape),
    ("the_independent", IndependentScraper.scrape),
    ("great_american_music_hall", GreatAmericanMusicHallScraper.scrape),
    ("cafe_du_nord", CafeDuNordScraper.scrape),
]
