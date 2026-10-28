"""
Per-venue scrapers for the music listings. Each one fetches a venue's
calendar page and parses it into `MusicEvent`s (see music_scraper.py).

`parse` methods take the page HTML (and, where the page omits the year, the
current date) so they can be tested against saved copies of the pages.
"""

import calendar
import json
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

# Placeholder lineup entries that aren't real artists ("TBA", "support tba").
PLACEHOLDER_ARTISTS = re.compile(
    r"^((special\s+)?(support|supporting|opener|openers|guests?)\s+)?(tba|tbd)?$",
    re.IGNORECASE,
)

# Listing text that means the show isn't happening at the venue as listed.
NOT_HAPPENING = re.compile(r"\b(CLOSED|CANCEL+ED|POSTPONED|MOVED)\b", re.IGNORECASE)

# Multi-day/multi-show passes are listed alongside the shows they cover
# ("Two Gallants: Two-Day Pass", "*3-Show Pass*"); they aren't separate shows.
TICKET_PASS = re.compile(
    r"\b(\d+|two|three|four)[\s-](day|show|night)\s+pass\b", re.IGNORECASE
)

# Venue rentals and holds (e.g. GAMH's "PRIVATE EVENT") aren't public shows.
PRIVATE_EVENT = re.compile(r"\bprivate\s+(events?|party)\b", re.IGNORECASE)


def _skip_reason(title: str, status: str = "") -> str | None:
    """
    Why a listing isn't a public show to list, or None if it is. `status` is
    the ticket button / status text ("Buy Tickets", "POSTPONED", ...).
    """
    if NOT_HAPPENING.search(title) or NOT_HAPPENING.search(status):
        return f"cancelled/postponed/moved ({status or title})"
    if TICKET_PASS.search(title):
        return "a ticket pass"
    if PRIVATE_EVENT.search(title):
        return "a private event"
    if re.search(r"event passed", status, re.IGNORECASE):
        return "already past"
    return None


def _artists(names: List[str]) -> List[Artist]:
    return [Artist(name=n) for n in names if not PLACEHOLDER_ARTISTS.match(n.strip())]


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
        if PRIVATE_EVENT.search(title):
            return None

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
                if PLACEHOLDER_ARTISTS.match(name) or name.startswith("..."):
                    current = None
                    continue
                current = Artist(name=name)
                artists.append(current)
            elif current is not None and not current.genre:
                current.genre = text
        return artists


# ----------------------------------------------------------------------
# TicketWeb "event discovery" WordPress plugin
# (The Independent, Brick & Mortar Music Hall)
# ----------------------------------------------------------------------


class TicketWebPluginScraper:
    """
    Scrape a venue site built on TicketWeb's "event discovery" WordPress plugin.

    One .tw-section per show, with the date as "M.D" (no year), "Show: 8:00 PM"
    (and on some themes "Doors: 7:00PM", age and price), and the status in the
    ticket button ("Buy Tickets", "Sold Out!", "POSTPONED", ...). Listings may
    be split across pages linked by a "Next »" (a.next.page-numbers) link.
    """

    VENUE: Venue
    URL: str
    MAX_PAGES = 50  # guard against a pagination loop

    @classmethod
    def scrape(cls) -> List[MusicEvent]:
        events, url, seen = [], cls.URL, set()
        while url and url not in seen and len(seen) < cls.MAX_PAGES:
            seen.add(url)
            html = fetch_html(url)
            events.extend(cls.parse(html))
            url = cls.next_page(html)
        print(f"  {cls.VENUE.slug}: {len(seen)} page(s)")
        return events

    @staticmethod
    def next_page(html: str) -> str | None:
        link = BeautifulSoup(html, "html.parser").select_one("a.next.page-numbers")
        return link.get("href") if link else None

    @classmethod
    def parse(cls, html: str, today: date | None = None) -> List[MusicEvent]:
        soup = BeautifulSoup(html, "html.parser")
        events = []
        for item in soup.select(".tw-section"):
            try:
                event = cls._parse_event(item, today)
            except ValueError as e:
                print(f"  {cls.VENUE.slug}: skipping unparseable event: {e}")
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
        reason = _skip_reason(title, status)
        if reason:
            print(f"  {cls.VENUE.slug}: skipping {title!r}: {reason}")
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
        doors = _parse_12h_time(cls._text(item, ".tw-event-door-time")) or ""

        support = [
            _clean(s.get_text())
            for s in item.select(".tw-attractions span")
            if _clean(s.get_text())
        ]
        names = [title] + support
        if not support and "," in title:
            # some themes list the openers in the name: "Hayden Everett, Jackson Lundy"
            names = _split_lineup(title)
            title = names[0]

        age_el = item.select_one(".tw-age-restriction")
        age = price = ""
        if age_el is not None:
            price = cls._text(age_el, ".tw-price")
            age = _normalize_age(_clean(age_el.get_text(" ").replace(price, "")))

        name_link = item.select_one(".tw-name a")
        ticket = item.select_one("a.tw-buy-tix-btn")
        img = item.select_one(".tw-image img")
        image = ""
        if img is not None and "default-event-img" not in (img.get("class") or []):
            image = img.get("src", "")

        buy_classes = ticket.get("class", []) if ticket else []
        return cls.VENUE.event(
            event_date,
            start,
            title,
            doors=doors,
            tagline=cls._text(item, ".tw-prefix"),
            artists=_artists(names),
            age=age,
            price=price,
            ticket_link=ticket.get("href", "") if ticket else "",
            link=name_link.get("href", "") if name_link else cls.URL,
            image=image,
            sold_out="tw_soldout" in buy_classes
            or bool(re.search(r"sold\s*out", status, re.IGNORECASE)),
        )


class IndependentScraper(TicketWebPluginScraper):
    """https://www.theindependentsf.com/ (all shows on one page)."""

    VENUE = Venue(
        slug="the_independent",
        link="https://www.theindependentsf.com/",
        area="western_addition",
        address="628 Divisadero St, San Francisco, CA 94117",
        map_link="https://maps.app.goo.gl/XdbVBeLgAVTwJkD99",
    )
    URL = "https://www.theindependentsf.com/"


class BrickAndMortarScraper(TicketWebPluginScraper):
    """https://www.brickandmortarmusic.com/ (paginated: /page/2/, /page/3/, ...)."""

    VENUE = Venue(
        slug="brick_and_mortar_music_hall",
        link="https://www.brickandmortarmusic.com/",
        area="mission",
        address="1710 Mission St, San Francisco, CA 94103",
        map_link="https://maps.app.goo.gl/Qh7SRQEm2BjrUkeY6",
    )
    URL = "https://www.brickandmortarmusic.com/"


# ----------------------------------------------------------------------
# SeeTickets WordPress plugin, calendar view
# (Great American Music Hall, The Chapel, Rickshaw Stop)
# ----------------------------------------------------------------------


def _unwrap_link(url: str) -> str:
    """Undo Proofpoint URL Defense rewriting: urldefense.com/v3/__<url>__;..."""
    m = re.match(r"https?://urldefense\.com/v3/__(.+?)__;", url)
    return m.group(1) if m else url


class SeeTicketsCalendarScraper:
    """
    Scrape a SeeTickets WordPress plugin calendar page.

    The page renders month grids: a "October 2026" heading
    (.seetickets-calendar-year-month-container) before each <table>, and each
    show as a .seetickets-calendar-event-container inside the <td> for its day
    (.date-number). The calendar holds every upcoming show, unlike the paged
    list view, which shows 12-15 at a time (checked against the fully
    clicked-through list for GAMH and The Chapel).

    Wording varies by site: "Event Showtime: 8:00PM" / "Show at 8:00PM",
    "with A, B" / "Supporting Talent: A, B".
    """

    VENUE: Venue
    URL: str

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
                print(f"  {cls.VENUE.slug}: skipping month with heading {heading!r}")
                continue
            for card in table.select(".seetickets-calendar-event-container"):
                try:
                    event = cls._parse_event(card, month_start)
                except ValueError as e:
                    print(f"  {cls.VENUE.slug}: skipping unparseable event: {e}")
                    continue
                if event is not None:
                    events.append(event)
        return events

    @classmethod
    def _parse_event(cls, card: Tag, month_start: datetime) -> MusicEvent | None:
        title_link = card.select_one(".seetickets-calendar-event-title a")
        title = _clean(title_link.get_text(" ")) if title_link else ""
        if not title:
            raise ValueError("no title")
        button = card.select_one(".seetickets-buy-btn")
        status = _clean(button.get_text(" ")) if button else ""
        reason = _skip_reason(title, status)
        if reason:
            print(f"  {cls.VENUE.slug}: skipping {title!r}: {reason}")
            return None

        day = card.find_parent("td").select_one(".date-number")
        try:
            event_date = month_start.replace(day=int(day.get_text(strip=True)))
        except (AttributeError, ValueError):
            raise ValueError(f"{title!r}: no day number")

        times = {}
        for p in card.select(".seetickets-calendar-event-date p"):
            m = re.match(
                r"(?:Event\s+)?(Show|Door)s?(?:time)?(?::|\s+at)\s*(.+)",
                _clean(p.get_text(" ")),
                re.IGNORECASE,
            )
            if m:
                times[m.group(1).lower()] = _parse_12h_time(m.group(2))
        start = times.get("show") or times.get("door")
        if not start:
            raise ValueError(f"{title!r}: no time")

        support = card.select_one(".supporting-talent")
        support_text = re.sub(
            r"^\s*Supporting Talent:\s*", "", support.get_text(" ") if support else ""
        )
        img = card.select_one("img.seetickets-calendar-event-picture")
        ticket_link = _unwrap_link(title_link.get("href", ""))
        return cls.VENUE.event(
            event_date.strftime("%Y-%m-%d"),
            start,
            title,
            doors=times.get("door") or "",
            artists=_artists([title] + _split_lineup(support_text)),
            ticket_link=ticket_link,
            link=ticket_link,
            image=img.get("src", "") if img else "",
            # "button-soldout" also styles "More Info" buttons (ticketed
            # elsewhere, not on sale yet), so go by the button text
            sold_out=bool(re.search(r"sold\s*out", status, re.IGNORECASE)),
        )


class GreatAmericanMusicHallScraper(SeeTicketsCalendarScraper):
    """https://gamh.com/calendar/"""

    VENUE = Venue(
        slug="great_american_music_hall",
        link="https://gamh.com/",
        area="tenderloin",
        address="859 O'Farrell St, San Francisco, CA 94109",
        map_link="https://maps.app.goo.gl/jAubki6ZFpdcDQ4UA",
    )
    URL = "https://gamh.com/calendar/"


class ChapelScraper(SeeTicketsCalendarScraper):
    """
    https://thechapelsf.com/calendar/ — the same shows as the 15-per-page list
    at /music/, all on one page.
    """

    VENUE = Venue(
        slug="the_chapel",
        link="https://thechapelsf.com/music/",
        area="mission",
        address="777 Valencia St, San Francisco, CA 94110",
        map_link="https://maps.app.goo.gl/SEXZAnkcLjLVDEbQA",
    )
    URL = "https://thechapelsf.com/calendar/"


class RickshawStopScraper(SeeTicketsCalendarScraper):
    """
    Rickshaw Stop's calendar page, fetched through the WordPress REST API.

    The site's HTML pages sit behind a Cloudflare rule that answers 403 to
    scripts (and headless browsers), but /wp-json/ is open and robots.txt
    allows it. The API returns the calendar page's rendered content, which
    is the same SeeTickets month-grid HTML a visitor sees.
    """

    VENUE = Venue(
        slug="rickshaw_stop",
        link="https://rickshawstop.com/",
        area="hayes_valley",
        address="155 Fell St, San Francisco, CA 94102",
        map_link="https://maps.app.goo.gl/9HgBeK9qsyk4S7gH8",
    )
    URL = "https://rickshawstop.com/wp-json/wp/v2/pages?slug=calendar&_fields=content"

    @classmethod
    def scrape(cls) -> List[MusicEvent]:
        return cls.parse_api(fetch_html(cls.URL))

    @classmethod
    def parse_api(cls, text: str) -> List[MusicEvent]:
        """Parse the API response: a JSON list of pages with content.rendered."""
        pages = json.loads(text)
        if isinstance(pages, dict):  # single page (/pages/<id>) rather than a list
            pages = [pages]
        if not pages:
            raise ValueError("no 'calendar' page in the WordPress API")
        return cls.parse(pages[0]["content"]["rendered"])


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
        reason = _skip_reason(title, status.replace("-", " "))
        if reason:
            print(f"  Cafe du Nord: skipping {title!r}: {reason}")
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


# ----------------------------------------------------------------------
# Another Planet Entertainment venue sites
# (The Fox Oakland, The Greek Theatre)
# ----------------------------------------------------------------------


class AnotherPlanetScraper:
    """
    Scrape an Another Planet Entertainment venue site's upcoming-shows list.

    One .mix.detail-information card per show, with a full start date in
    .single-date-show[content] ("November 6, 2026 8:00 pm"), doors/show
    times, a tour line (.topline), and a Ticketmaster button (class
    "soldout" when sold out). The list holds every upcoming show; it matches
    the site's /calendar/ page.

    Some sites mark the list and start date up differently, so subclasses can
    override CARD_SELECTOR and DATE_SELECTOR.
    """

    VENUE: Venue
    URL: str
    CARD_SELECTOR = ".upcoming-events-list .mix.detail-information"
    DATE_SELECTOR = ".single-date-show"

    @classmethod
    def scrape(cls) -> List[MusicEvent]:
        return cls.parse(fetch_html(cls.URL))

    @classmethod
    def parse(cls, html: str) -> List[MusicEvent]:
        soup = BeautifulSoup(html, "html.parser")
        events = []
        for card in soup.select(cls.CARD_SELECTOR):
            try:
                event = cls._parse_event(card)
            except ValueError as e:
                print(f"  {cls.VENUE.slug}: skipping unparseable event: {e}")
                continue
            if event is not None:
                events.append(event)
        return events

    @classmethod
    def _parse_event(cls, card: Tag) -> MusicEvent | None:
        title_el = card.select_one(".show-title")
        title = _clean(title_el.get_text(" ")) if title_el else ""
        if not title:
            raise ValueError("no title")
        buttons = card.select(".event-data a.button")
        ticket = next(
            (b for b in buttons if "more-info" not in b.get("class", [])), None
        )
        status = _clean(ticket.get_text(" ")) if ticket else ""
        reason = _skip_reason(title, status)
        if reason:
            print(f"  {cls.VENUE.slug}: skipping {title!r}: {reason}")
            return None

        if card.select_one(".event__start-time") is None:
            # Multi-day festivals list "Dates: Mar 11, 12, 13" instead of a time
            print(f"  {cls.VENUE.slug}: skipping {title!r}: no show time")
            return None
        when = card.select_one(cls.DATE_SELECTOR)
        try:
            # "November 6, 2026 8:00 pm", or "8:00pm" without the space
            content = re.sub(r"(\d)([ap]m)$", r"\1 \2", _clean(when.get("content", "")))
            start = datetime.strptime(content.upper(), "%B %d, %Y %I:%M %p")
        except (AttributeError, ValueError):
            raise ValueError(f"{title!r}: bad start {when and when.get('content')!r}")
        doors_el = card.select_one(".event__doors-open")
        doors = (
            _parse_12h_time(_clean(doors_el.get_text()).rstrip("| "))
            if doors_el
            else None
        )

        link = card.select_one(".entry a")
        topline = card.select_one(".topline")
        img = card.select_one("img")
        return cls.VENUE.event(
            start.strftime("%Y-%m-%d"),
            start.strftime("%H%M"),
            title,
            doors=doors or "",
            tagline=_clean(topline.get_text(" ")) if topline else "",
            artists=_artists([title]),
            ticket_link=ticket.get("href", "") if ticket else "",
            link=link.get("href", "") if link else cls.URL,
            image=img.get("src", "") if img else "",
            sold_out=ticket is not None
            and ("soldout" in ticket.get("class", []) or "sold out" in status.lower()),
        )


class FoxOaklandScraper(AnotherPlanetScraper):
    """https://thefoxoakland.com/listing/"""

    VENUE = Venue(
        slug="the_fox_oakland",
        link="https://thefoxoakland.com/",
        area="oakland",
        address="1807 Telegraph Ave, Oakland, CA 94612",
        map_link="https://maps.app.goo.gl/9NnVYcSmi9eaRM8w8",
    )
    URL = "https://thefoxoakland.com/listing/"


class GreekTheatreScraper(AnotherPlanetScraper):
    """https://thegreekberkeley.com/ (the home page lists every upcoming show)"""

    VENUE = Venue(
        slug="the_greek_theatre",
        link="https://thegreekberkeley.com/",
        area="berkeley",
        address="2001 Gayley Rd, Berkeley, CA 94720",
        map_link="https://maps.app.goo.gl/iyVscV6mbic3agZv5",
    )
    URL = "https://thegreekberkeley.com/"


class CastroScraper(AnotherPlanetScraper):
    """
    https://thecastro.com/event_category/music (every upcoming music event).
    The Castro also shows films; cinema_scraper reads FILM_URL.
    """

    VENUE = Venue(
        slug="the_castro_theatre",
        link="https://thecastro.com/",
        area="castro",
        address="429 Castro St, San Francisco, CA 94114",
        map_link="https://maps.app.goo.gl/oQtq7c7pvUFNFycVA",
    )
    URL = "https://thecastro.com/event_category/music"
    FILM_URL = "https://thecastro.com/event_category/film"
    CARD_SELECTOR = ".upcoming-events-cat-list .mix.detail-information"
    DATE_SELECTOR = ".date-show"


SCRAPERS = [
    ("bottom_of_the_hill", BottomOfTheHillScraper.scrape),
    ("the_independent", IndependentScraper.scrape),
    ("brick_and_mortar_music_hall", BrickAndMortarScraper.scrape),
    ("great_american_music_hall", GreatAmericanMusicHallScraper.scrape),
    ("the_chapel", ChapelScraper.scrape),
    ("rickshaw_stop", RickshawStopScraper.scrape),
    ("cafe_du_nord", CafeDuNordScraper.scrape),
    ("the_fox_oakland", FoxOaklandScraper.scrape),
    ("the_greek_theatre", GreekTheatreScraper.scrape),
    ("the_castro_theatre", CastroScraper.scrape),
]
