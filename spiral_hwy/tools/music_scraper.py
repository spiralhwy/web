#!/usr/bin/env python3
"""
Scraper for live music listings.

Each venue scraper (see music_venues.py) turns a venue's calendar into a list
of `MusicEvent`s, a venue-agnostic representation that the music page and the
iCalendar feed (spiral_hwy_music_calendar.ics) are both rendered from. Unlike
movies, a show is only ever listed by one venue, so events are grouped by date
without any cross-venue merging.

Output shape (spiral_hwy/_data/music.json):
    [{"date": "YYYY-MM-DD", "events": [MusicEvent, ...]}, ...]
sorted by date, and by start time within each date.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List

import pytz
import requests
from web_scraper import atomic_write_bytes

USER_AGENT = "Mozilla/5.0 (compatible; SpiralHWY/1.0; +https://www.spiralhwy.com)"

PACIFIC_TZ = pytz.timezone("US/Pacific")


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


@dataclass(frozen=True)
class Venue:
    """
    Where a show is. `slug` is shown via the displayName filter
    ("cafe_du_nord" -> "Cafe du Nord") and used in event ids.
    """

    slug: str
    link: str
    area: str
    address: str
    map_link: str = ""  # Google Maps share link; defaults to an address search

    @property
    def map(self) -> str:
        return self.map_link or (
            "https://maps.google.com/?q=" + self.address.replace(" ", "+")
        )

    def event(self, date: str, time: str, title: str, **kwargs) -> MusicEvent:
        """Build a MusicEvent at this venue."""
        return MusicEvent(
            id=f"{self.slug}-{date.replace('-', '')}-{time}",
            venue=self.slug,
            venue_link=self.link,
            area=self.area,
            address=self.address,
            map=self.map,
            date=date,
            time=time,
            title=title,
            **kwargs,
        )


def _clean(text: str) -> str:
    """Collapse whitespace (including &nbsp;) and strip."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _parse_12h_time(text: str) -> str | None:
    """Convert '7:00PM' / '7:00 pm' / '7 PM' to '1900'."""
    m = re.fullmatch(
        r"(\d{1,2})(?::(\d{2}))?\s*([AP])\.?M\.?", text.strip(), re.IGNORECASE
    )
    if not m:
        return None
    hours, minutes, period = int(m.group(1)), m.group(2) or "00", m.group(3).upper()
    if not (1 <= hours <= 12):
        return None
    hours = hours % 12 + (12 if period == "P" else 0)
    return f"{hours:02d}{minutes}"


def _normalize_age(text: str) -> str:
    """'••• 21 AND OVER' -> '21+', '••• ALL AGES' / 'all-ages' -> 'All Ages'."""
    text = _clean(text.replace("•", ""))
    m = re.match(r"(\d+)\s*(\+|AND\s+OVER|AND\s+UP)", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}+"
    if re.fullmatch(r"ALL[\s-]AGES", text, re.IGNORECASE):
        return "All Ages"
    return text.title()


def _split_lineup(text: str) -> List[str]:
    """'with Houses of Heaven, False Figure' -> ['Houses of Heaven', 'False Figure']."""
    text = re.sub(r"^\s*(with|w/)\s+", "", _clean(text), flags=re.IGNORECASE)
    return [name for name in (n.strip() for n in text.split(",")) if name]


def infer_date(month: int, day: int, today: date | None = None) -> str | None:
    """
    Date for a listing that shows only month and day: the next occurrence on
    or after yesterday (allowing for shows that run past midnight).
    """
    if today is None:
        today = datetime.now(PACIFIC_TZ).date()
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:  # bad input, or Feb 29 outside a leap year
            continue
        if candidate >= today - timedelta(days=1):
            return candidate.isoformat()
    return None


def fetch_html(url: str, encoding: str | None = None) -> str:
    """GET a page and return its text."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    if encoding:
        resp.encoding = encoding
    return resp.text


def dedupe(events: List[MusicEvent]) -> List[MusicEvent]:
    """
    Drop events whose id was already seen. Ids are calendar UIDs, so two
    events sharing one would clobber each other in subscribers' calendars.
    """
    seen: dict[str, MusicEvent] = {}
    for e in events:
        if e.id in seen:
            print(
                f"  duplicate id {e.id}: dropping {e.title!r}, keeping {seen[e.id].title!r}"
            )
        else:
            seen[e.id] = e
    return list(seen.values())


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


def main():
    from music_venues import SCRAPERS

    flyer_dir = Path(__file__).parent.parent.parent / "public" / "flyers"

    events: List[MusicEvent] = []
    for name, fn in SCRAPERS:
        print("-" * 10, f"scrape {name}", "-" * 10)
        try:
            venue_events = fn()
            print(f"  {len(venue_events)} event(s)")
            events.extend(venue_events)
        except Exception as e:
            print("-" * 10, f"scrape failed {name}", "-" * 10)
            print(f"Exception:\n{e}")

    events = dedupe(events)
    for e in events:
        save_flyer(e, flyer_dir)

    json_path = Path(__file__).parent.parent / "_data" / "music.json"
    json_path.parent.mkdir(exist_ok=True, parents=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(group_by_date(events), f, indent=4, default=asdict)


if __name__ == "__main__":
    main()
