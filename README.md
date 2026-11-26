# Spiral HWY

Get to great art.


## Installations

1. [Node](https://nodejs.org/en/download/package-manager)
1. [Poetry](https://python-poetry.org/docs/#installation)
1. [Chrome](https://www.google.com/intl/en_au/chrome/dr/download/?brand=OZZY&ds_kid=43700080456228409&gad_source=1&gclsrc=ds)
1. Node modules: `npm install`
1. Poetry project: `poetry install`


## Usage

The `spiral-hwy` command (installed by `poetry install`) wraps the common tasks.
Run `poetry run spiral-hwy --help` for all options.

Scrape all listings (cinema + music):
```
poetry run spiral-hwy scrape
```

Scrape only one source, or run cinema scrapes in parallel:
```
poetry run spiral-hwy scrape cinema
poetry run spiral-hwy scrape music
poetry run spiral-hwy scrape cinema --workers 4
```

Serve the website locally (http://localhost:8080, live reload):
```
poetry run spiral-hwy serve
poetry run spiral-hwy serve --port 8081
```

Build the site into `public/`:
```
poetry run spiral-hwy build
```

The same commands are available as Poe tasks: `poetry run poe scrape`, `poetry run poe serve`.

Hydra config overrides can still be passed by running the cinema scraper directly:
```
poetry run ./spiral_hwy/tools/cinema_scraper.py veezi=test
```


## Data Collection

Movie posters are saved directly to `public/`. The listings information is saved to `spiral_hwy/_data/` to satisfy Eleventy templating file structure.


## Testing

Unit tests are in [`tests/`](spiral_hwy/tests) and hold saved websites that are used to mock the websites and compare against the ground truth. This ensures changes to the web scraper will not break previous configurations.
