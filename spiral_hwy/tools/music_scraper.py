#!/usr/bin/env python3
"""
Scraper for live music listings.

Each venue scraper turns a venue's calendar into a list of `MusicEvent`s, a
venue-agnostic representation that the music page and the iCalendar feed
(spiral_hwy_music_calendar.ics) are both rendered from. Unlike movies, a show is only ever listed
by one venue, so events are grouped by date without any cross-venue merging.

Output shape (spiral_hwy/_data/music.json):
    [{"date": "YYYY-MM-DD", "events": [MusicEvent, ...]}, ...]
sorted by date, and by start time within each date.
"""

import calendar
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

import requests
from bs4 import BeautifulSoup, Tag
from web_scraper import atomic_write_bytes

USER_AGENT = "Mozilla/5.0 (compatible; SpiralHWY/1.0; +https://www.spiralhwy.com)"

BOTH_URL = "https://www.bottomofthehill.com/calendar.html"
BOTH_VENUE = "bottom_of_the_hill"
BOTH_VENUE_LINK = "https://www.bottomofthehill.com/"
BOTH_AREA = "potrero_hill"
BOTH_ADDRESS = "1233 17th St, San Francisco, CA 94107"
BOTH_MAP = "https://maps.google.com/?q=1233+17th+St,+San+Francisco,+CA+94107"

MONTHS = "|".join(calendar.month_name[1:])

# Placeholder lineup entries that aren't real artists.
PLACEHOLDER_ARTISTS = {"", "tba", "tbd"}


@dataclass
class Artist:
    """
    Performer on a bill.
    """

    name: str
    genre: str = ""


@dataclass
class MusicEvent:
    """
    Single show at a venue, normalized across venues.

    `id` is stable across scrapes so it can be used as an iCalendar UID;
    calendar clients use it to update an event instead of duplicating it.
    Times are 24h "HHMM" strings in Pacific time, matching movies.json.
    """

    id: str
    venue: str
    venue_link: str
    area: str
    address: str
    map: str
    date: str
    time: str
    title: str
    doors: str = ""
    tagline: str = ""
    artists: List[Artist] = field(default_factory=list)
    age: str = ""
    price: str = ""
    ticket_link: str = ""
    link: str = ""
    image: str = ""
    sold_out: bool = False


def _clean(text: str) -> str:
    """Collapse whitespace (including &nbsp;) and strip."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _https(url: str) -> str:
    """Bottom of the Hill links are written as http:// but the site serves https."""
    return re.sub(r"^http://", "https://", url)


def _parse_12h_time(text: str) -> str | None:
    """Convert '7:00PM' / '7:00 pm' to '1900'."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})\s*([AP])M", text.strip(), re.IGNORECASE)
    if not m:
        return None
    hours, minutes, period = int(m.group(1)), m.group(2), m.group(3).upper()
    if not (1 <= hours <= 12):
        return None
    hours = hours % 12 + (12 if period == "P" else 0)
    return f"{hours:02d}{minutes}"


def _in_div(el: Tag, cell: Tag) -> bool:
    """Whether `el` sits inside a <div> nested within `cell`."""
    for parent in el.parents:
        if parent is cell:
            return False
        if parent.name == "div":
            return True
    return False


def _normalize_age(text: str) -> str:
    """'••• 21 AND OVER' -> '21+', '••• ALL AGES' -> 'All Ages'."""
    text = _clean(text.replace("•", ""))
    m = re.match(r"(\d+)\s+AND\s+OVER", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}+"
    if re.fullmatch(r"ALL AGES", text, re.IGNORECASE):
        return "All Ages"
    return text.title()


def group_by_date(events: List[MusicEvent]) -> list:
    """
    Group events into the [{"date", "events"}] shape the templates iterate over.
    """
    by_date: dict[str, list[MusicEvent]] = {}
    for e in sorted(events, key=lambda e: (e.date, e.time, e.venue)):
        by_date.setdefault(e.date, []).append(e)
    return [{"date": d, "events": evs} for d, evs in by_date.items()]


def save_flyer(event: MusicEvent, flyer_dir: Path) -> None:
    """
    Download the event's flyer into `flyer_dir` and point `event.image` at the
    local copy, so the site doesn't hotlink venue images. On failure the
    event is left without an image rather than dropped.
    """
    if not event.image:
        return
    save_path = flyer_dir / f"{event.id}.jpg"
    if not save_path.exists():
        try:
            resp = requests.get(
                event.image, headers={"User-Agent": USER_AGENT}, timeout=30
            )
            resp.raise_for_status()
            atomic_write_bytes(save_path, resp.content)
        except requests.RequestException as e:
            print(f"  flyer download failed for {event.id}: {e}")
            event.image = ""
            return
    event.image = f"{flyer_dir.name}/{save_path.name}"


class BottomOfTheHillScraper:
    """
    Scrape https://www.bottomofthehill.com/calendar.html.

    The calendar is one hand-maintained static HTML table: one <tr> per show,
    with cells for the flyer, the ticket button, the details (date, times, age,
    price, lineup — marked up with class="date|time|age|cover|for|band|genre"),
    and a Facebook link.
    """

    @staticmethod
    def fetch() -> str:
        resp = requests.get(BOTH_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        # Page is declared ISO-8859-1; requests' guess can differ.
        resp.encoding = "iso-8859-1"
        return resp.text

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
        if re.search(r"\b(CLOSED|CANCEL+ED|POSTPONED)\b", time_text, re.IGNORECASE):
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

        return MusicEvent(
            id=f"{BOTH_VENUE}-{date.replace('-', '')}-{start}",
            venue=BOTH_VENUE,
            venue_link=BOTH_VENUE_LINK,
            area=BOTH_AREA,
            address=BOTH_ADDRESS,
            map=BOTH_MAP,
            date=date,
            time=start,
            doors=doors,
            title=title,
            tagline=taglines[0] if artists and taglines else "",
            artists=artists,
            age=age,
            price=price,
            ticket_link=ticket_link,
            link=link or BOTH_URL,
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


def scrape_bottom_of_the_hill() -> List[MusicEvent]:
    return BottomOfTheHillScraper.parse(BottomOfTheHillScraper.fetch())


def main():
    tasks = [
        ("bottom_of_the_hill", scrape_bottom_of_the_hill),
    ]
    flyer_dir = Path(__file__).parent.parent.parent / "public" / "flyers"

    events: List[MusicEvent] = []
    for name, fn in tasks:
        print("-" * 10, f"scrape {name}", "-" * 10)
        try:
            venue_events = fn()
            print(f"  {len(venue_events)} event(s)")
            events.extend(venue_events)
        except Exception as e:
            print("-" * 10, f"scrape failed {name}", "-" * 10)
            print(f"Exception:\n{e}")

    for e in events:
        save_flyer(e, flyer_dir)

    json_path = Path(__file__).parent.parent / "_data" / "music.json"
    json_path.parent.mkdir(exist_ok=True, parents=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(group_by_date(events), f, indent=4, default=asdict)


if __name__ == "__main__":
    main()
