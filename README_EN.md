# Species 2000 China Animal Information Crawler

This project is a Python-based crawler for collecting animal species information from Species 2000 China / CoL China related pages. It focuses on extracting three core text fields from species detail pages: **Morphological Description**, **Biology**, and **Ecology**. Each species is saved as an individual TXT file for downstream text mining, knowledge extraction, and knowledge graph construction.

The crawler targets `http://col.especies.cn/CoLChina` and its corresponding Species 2000 China taxonomy tree pages. In the script, the default taxonomy-tree entry is `http://www.especies.cn/baike/taxon/sp2000TaxaTree_2023/`. By configuring target taxon names, it can recursively traverse multi-level animal classification pages and collect species-level descriptions.

## Features

- Recursively traverses the taxonomy tree from configurable target taxa.
- Supports multi-level classification pages, such as class, order, family, genus, and species levels.
- Handles paginated classification tables to avoid missing records.
- Supports resumable crawling by recording completed species URLs.
- Uses Selenium with Microsoft Edge to simulate real browser behavior.
- Includes page loading retries, key-element waits, request delays, and debug HTML saving.
- Extracts description data from both asynchronous API responses and rendered DOM content.
- Cleans HTML tags, redundant headings, special symbols, and invalid text.
- Saves one standardized TXT file per species, named primarily by Chinese species name.

## Tech Stack

- Python 3
- Selenium
- Microsoft Edge WebDriver
- webdriver-manager
- BeautifulSoup4
- Regular expressions
- JavaScript DOM / Fetch calls

## Project Structure

```text
.
|-- get_info.py                  # Main crawler script
|-- species_data/                # Default output directory for species TXT files
|-- crawled_species_urls.txt     # Resume record for completed species URLs
`-- debug_pages/                 # Saved debug HTML pages
```

The `species_data/`, `crawled_species_urls.txt`, and `debug_pages/` paths are generated automatically when needed.

## Installation

```bash
pip install -U selenium webdriver-manager beautifulsoup4
```

Before running the crawler, make sure Microsoft Edge is installed and that a compatible Edge WebDriver is available. The script supports both a manually configured local `msedgedriver.exe` path and automatic driver management through `webdriver-manager` or Selenium Manager.

## Usage

```bash
python get_info.py
```

After startup, the script builds start URLs from the taxa configured in `TARGET_TAXA`, recursively traverses child taxa, and extracts description fields from species detail pages.

## Key Configuration

You can adjust the following parameters near the top of `get_info.py`:

```python
BASE_URL = "http://www.especies.cn/baike/taxon/sp2000TaxaTree_2023/"

TARGET_TAXA = [
    "Mammalia",
    "Reptilia",
]

OUTPUT_DIR = "species_data"
CRAWLED_RECORD_FILE = "crawled_species_urls.txt"

REQUEST_DELAY_SECONDS = 1
PAGE_WAIT_SECONDS = 18
MAX_RETRIES = 3
HEADLESS = True
EDGEDRIVER_PATH = "C:/path/to/msedgedriver.exe"
```

Common options:

- `TARGET_TAXA`: Target taxa to crawl, such as `Mammalia`, `Reptilia`, `Chordata`, or `Arthropoda`.
- `OUTPUT_DIR`: Directory for output TXT files.
- `CRAWLED_RECORD_FILE`: File used to record successfully crawled species URLs for resume support.
- `REQUEST_DELAY_SECONDS`: Delay between requests. Increase this value if access becomes unstable.
- `PAGE_WAIT_SECONDS`: Maximum wait time for key page elements.
- `MAX_RETRIES`: Maximum retry count for failed page loads.
- `HEADLESS`: Whether to run Edge in headless mode.
- `EDGEDRIVER_PATH`: Local EdgeDriver path. If empty, the script attempts to use `webdriver-manager` or Selenium Manager.

## Output Format

Each species is saved as an individual TXT file. The filename uses the Chinese species name when available. The file content follows a fixed structure:

```text
【形态描述】
...

【生物学】
...

【生态学】
...
```

The section titles above are kept in Chinese to match the actual script output. If a field cannot be extracted, the script writes a placeholder value so all output files remain structurally consistent.

## Implementation Overview

### 1. Recursive Taxonomy Traversal and Automatic Pagination

The crawler first loads the target taxon page, parses the classification table with BeautifulSoup, and extracts rank, Latin name, Chinese name, and detail URL. Non-species nodes are visited recursively, while species nodes trigger detail-page extraction.

Because a classification page may contain multiple pages of table records, the script detects DataTables pagination information, pagination buttons, or total-record text from the page, calculates the total page count, switches pages automatically, and merges child records with URL-level deduplication.

### 2. Anti-Crawling and Page Stability Handling

The crawler uses Microsoft Edge through Selenium to behave like a real browser. It configures a realistic User-Agent, HTTP headers, window size, automation-feature hiding, direct proxy settings, and proxy-environment cleanup to improve page access reliability.

It also includes request delays, retry logic, key-element waiting, timeout handling, and redirected-page logging. When species content cannot be extracted, the current HTML can be saved to `debug_pages/` for troubleshooting.

### 3. Field Extraction, Text Cleaning, and Standardized Output

Species description content may come from asynchronous API data or from the rendered front-end DOM. The script first calls the description API from within the browser context to obtain structured data. If some fields are still missing, it clicks the description tab and falls back to DOM parsing.

After extraction, BeautifulSoup is used to remove HTML tags, and regular expressions are used to clean headings, redundant prefixes, and special symbols. The cleaned fields are then written to TXT files in a fixed format. Existing non-empty output files can be skipped to avoid duplicated work.

## Resume Support

Successfully processed species URLs are appended to `crawled_species_urls.txt`. On the next run, the script reads this file and skips completed species, allowing interrupted crawls to continue.

To crawl everything from scratch, remove:

```text
crawled_species_urls.txt
species_data/
```

## Notes

- Please respect the target website's robots rules, rate limits, and data usage policies.
- For large-scale crawling, increase `REQUEST_DELAY_SECONDS` and split `TARGET_TAXA` into smaller batches.
- If timeouts or redirects occur frequently, disable headless mode for debugging or increase wait times.
- If EdgeDriver fails to start, check the Edge browser version, driver version, and `EDGEDRIVER_PATH`.
- When publishing to GitHub, avoid committing large crawled datasets, debug HTML files, or machine-specific local paths.

## Use Cases

- Animal species description corpus collection
- Biological text data preparation
- Knowledge extraction preprocessing
- Species knowledge graph source data preparation
- Experiments on taxonomy-tree traversal and web crawling

