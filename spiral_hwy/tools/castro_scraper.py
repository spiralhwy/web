#!/usr/bin/env python3
"""
Scraper for film screenings at The Castro.

The Castro's film page uses the same Another Planet event cards as its music
page, so the cards are parsed by music_venues.CastroScraper and each one is
turned into a showing in a Castro movie listing.
"""

import base64
from pathlib import Path

import requests
from cinema_scraper import MovieListing, MovieShowing, atomic_write_bytes
from music_scraper import fetch_bytes, fetch_html
from music_venues import CastroScraper

CASTRO_THEATER = CastroScraper.VENUE.slug
CASTRO_THEATER_LINK = CastroScraper.VENUE.link
CASTRO_AREA = CastroScraper.VENUE.area
CASTRO_MAP = CastroScraper.VENUE.map


def parse_films(html: str, poster_dir: Path | None = None) -> dict:
    """
    Parse the film page into listings shaped like `CinemaScraper.listings`:
        {date: {title: {"poster": ..., "rating": ..., "listings": [...]}}}
    Posters are downloaded into `poster_dir` when one is given.
    """
    listings: dict = {}
    for event in CastroScraper.parse(html):
        poster_key = base64.urlsafe_b64encode(event.title.lower().encode()).decode(
            "utf-8"
        )
        if poster_dir is not None:
            _save_poster(event.image, poster_dir / f"{poster_key}.png")

        showing = MovieShowing(
            available="SOLD OUT" if event.sold_out else "",
            link=event.ticket_link or event.link,
            time=event.time,
        )
        date_dict = listings.setdefault(event.date, {})
        title_dict = date_dict.setdefault(
            event.title, {"poster": poster_key, "rating": "", "listings": []}
        )
        # Several screenings of one film on a day share the Castro listing
        castro = next(
            (l for l in title_dict["listings"] if l.theater == CASTRO_THEATER), None
        )
        if castro is None:
            title_dict["listings"].append(
                MovieListing(
                    showings=[showing],
                    theater=CASTRO_THEATER,
                    map=CASTRO_MAP,
                    area=CASTRO_AREA,
                    theater_link=CASTRO_THEATER_LINK,
                )
            )
        else:
            castro.showings.append(showing)
            castro.showings.sort(key=lambda s: s.time)
    return listings


def _save_poster(src: str, save_path: Path) -> None:
    """Download a poster if it isn't saved yet; leave it missing on failure."""
    if not src or save_path.exists():
        return
    save_path.parent.mkdir(exist_ok=True, parents=True)
    try:
        atomic_write_bytes(save_path, fetch_bytes(src))
    except requests.RequestException as e:
        print(f"  Castro: poster download failed for {src}: {e}")


def scrape_castro(poster_dir: Path) -> dict:
    return parse_films(fetch_html(CastroScraper.FILM_URL), poster_dir)
