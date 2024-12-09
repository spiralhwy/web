# Spiral HWY

Get to great art.


## Install / Usage

1. [Install Node](https://nodejs.org/en/download/package-manager)
1. [Install Poetry](https://python-poetry.org/docs/#installation)
1. [Install Chrome](https://www.google.com/intl/en_au/chrome/dr/download/?brand=OZZY&ds_kid=43700080456228409&gad_source=1&gclsrc=ds)

Install node modules:
```
npm install
```

Install Poetry:
```
poetry install
```

Build the project:
```
npx eleventy
```

Host locally:
```
npx eleventy --serve
```


Run scraper locally:
```
poetry run ./spiral_hwy/tools/web_scraper.py
```

Serve Eleventy website:
```
poetry poe serve
```


Install [Poetry](https://python-poetry.org/docs/#installation)
Install [PoeThePoet](https://pipx.pypa.io/stable/)
CSS linter: [StyleLint](https://stylelint.io/user-guide/get-started)


## Data Collection

Movie posters are saved directly to `public/`. The listings information is saved to `spiral_hwy/_data/` to satisfy Eleventy templating file structure.


## Testing

Unit tests are in [`tests/`](spiral_hwy/tests) and hold saved websites that are used to mock the websites and compare against the ground truth. This ensures changes to the web scraper will not break previous configurations.
