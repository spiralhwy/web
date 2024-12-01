# Spiral HWY

Get to great art.


## Install / Usage

Install node modules:
```
npm install
```

Build the project:
```
npx eleventy
```

Host locally:
```
npx eleventy --serve
```

Install Poetry:
```
poetry install
```

Run scraper locally:
```
poetry run ./spiral_hwy/tools/web_scraper.py 
```


Install [Poetry](https://python-poetry.org/docs/#installation)
Install [PoeThePoet](https://pipx.pypa.io/stable/)
CSS linter: [StyleLint](https://stylelint.io/user-guide/get-started)


## Data Collection

Movie posters are saved directly to `public/`. The listings information is saved to `spiral_hwy/_data/` to satisfy Eleventy templating file structure.

## Bugs

Not showing listings at all for sold out times

## Testing

Unit tests are in [`tests/`](spiral_hwy/tests) and hold saved websites that are used to mock the websites and compare against the ground truth. This ensures changes to the web scraper will not break previous configurations.
