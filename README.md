# Spiral HWY

Get to great art.


## Installations

1. [Node](https://nodejs.org/en/download/package-manager)
1. [Poetry](https://python-poetry.org/docs/#installation)
1. [Chrome](https://www.google.com/intl/en_au/chrome/dr/download/?brand=OZZY&ds_kid=43700080456228409&gad_source=1&gclsrc=ds)
1. Node modules: `npm install`
1. Poetry project: `poetry install`


## Usage

Run scraper locally:
```
poetry run ./spiral_hwy/tools/web_scraper.py
```

Build the project:
```
npx eleventy
```

Host locally:
```
npx eleventy --serve
```

Serve Eleventy website (same as above):
```
poetry poe serve
```


## Data Collection

Movie posters are saved directly to `public/`. The listings information is saved to `spiral_hwy/_data/` to satisfy Eleventy templating file structure.


## Testing

Unit tests are in [`tests/`](spiral_hwy/tests) and hold saved websites that are used to mock the websites and compare against the ground truth. This ensures changes to the web scraper will not break previous configurations.
