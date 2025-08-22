import argparse
import datetime
import logging
import os
import re
import secrets
import string
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import yaml  # type: ignore
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.style import Style
from rich.table import Table
from rich.theme import Theme
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from tqdm import tqdm
from utils import int_list_to_str, mean, run_with_timeout, std

TIMEOUT_DURATION = 120  # The OR website is weird sometimes
CONFIG_FILE = "./conf.yaml"


def setup_logger(debug: bool = False) -> None:
    logging_level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        level=logging_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                rich_tracebacks=True,
                show_time=True,
                show_level=True,
                show_path=False,
                markup=True,
                console=Console(
                    theme=Theme(
                        {
                            "logging.level.debug": Style(color="blue"),
                            "logging.level.info": Style(color="green"),
                            "logging.level.warning": Style(color="yellow", bold=True),
                            "logging.level.error": Style(color="red"),
                            "logging.level.critical": Style(
                                color="white", bgcolor="red", bold=True
                            ),
                        }
                    )
                ),
            )
        ],
    )


@dataclass
class ConferenceConfig:
    """Configuration for a specific conference."""

    url: str
    rating_config: dict[str, Any]
    confidence_config: dict[str, Any]
    final_rating_config: dict[str, Any]


@dataclass
class BrowserConfig:
    """Configuration for the browser used by Selenium."""

    firefox_binary: Optional[str] = None
    geckodriver_path: Optional[str] = None
    window_size: Optional[tuple[int, int]] = None
    additional_args: Optional[list[str]] = None


@dataclass
class Submission:
    """Class containing submission details."""

    title: str  # Title.
    sub_id: str  # Paper ID.
    ratings: list[int]  # List of reviewer ratings.
    confidences: list[int]  # List of reviewer confidences.
    final_ratings: list[int]  # List of final reviewer ratings.

    def __repr__(self) -> str:
        return f"Submission({self.sub_id}, {self.title}, {self.ratings}, {self.confidences})"

    def __str__(self) -> str:
        return f"{self.sub_id}, {self.title}, *, {int_list_to_str(self.ratings)}, *, {int_list_to_str(self.final_ratings)}"

    def info(self) -> str:
        return (
            f"ID: {self.sub_id}, {self.title}, "
            + f"Ratings: {self.ratings}, "
            + f"Avg: {np.mean(self.ratings):.2f}, "
            + f"Var: {np.var(self.ratings):.2f}"
        )


class ConfigLoader:
    """Loads and manages conference configurations."""

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.browser_config: Optional[BrowserConfig] = None
        self.configs = self._load_configs()

    def _load_configs(self) -> dict[str, ConferenceConfig]:
        """Load configurations from YAML file."""
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Configuration file {self.config_file} not found!")

        with open(self.config_file) as f:
            data = yaml.safe_load(f)

        configs = {}
        for conf_name, conf_data in data["conferences"].items():
            configs[conf_name] = ConferenceConfig(
                url=conf_data["url"],
                rating_config=conf_data.get("rating", {}),
                confidence_config=conf_data.get("confidence", {}),
                final_rating_config=conf_data.get("final_rating", {}),
            )

        if "browser" in data:
            print("Here")
            browser_config = data["browser"]
            print(browser_config)
            self.browser_config = BrowserConfig(
                firefox_binary=(
                    browser_config["firefox_binary" or None]
                    if "firefox_binary" in browser_config
                    else None
                ),
                geckodriver_path=(
                    browser_config["geckodriver_path" or None]
                    if "geckodriver_path" in browser_config
                    else None
                ),
                window_size=(
                    tuple(browser_config["window_size"])
                    if "window_size" in browser_config
                    else None
                ),
                additional_args=(
                    browser_config["additional_args"]
                    if "additional_args" in browser_config
                    else None
                ),
            )

        return configs

    def get_config(self, conf_name: str) -> ConferenceConfig:
        """Get configuration for a specific conference."""
        if conf_name not in self.configs:
            raise ValueError(
                f"Conference '{conf_name}' not found in configuration. Available: {list(self.configs.keys())}"
            )
        return self.configs[conf_name]

    def list_conferences(self) -> list[str]:
        """List all available conferences."""
        return list(self.configs.keys())


class TextExtractor:
    """Utility class for extracting values from text based on configuration."""

    @staticmethod
    def extract_first_number(
        text: str, start_text: str, end_text: Optional[str] = None
    ) -> Optional[int]:
        """Extract the first number found after start_text."""
        start_idx = text.find(start_text)
        if start_idx == -1:
            return None

        search_start = start_idx + len(start_text)

        if end_text:
            end_idx = text.find(end_text, search_start)
            if end_idx == -1:
                search_text = text[search_start:]
            else:
                search_text = text[search_start:end_idx]
        else:
            search_text = text[search_start:]

        match = re.search(r"\d+", search_text)
        if match:
            return int(match.group())

        return None

    @staticmethod
    def extract_value(text: str, config: dict[str, Any]) -> Optional[int]:
        """Extract value based on configuration."""
        if not config or not config.get("start_text"):
            return None

        method = config.get("extract_method", "first_number")

        if method == "first_number":
            return TextExtractor.extract_first_number(
                text, config["start_text"], config.get("end_text")
            )

        return None


class ORAPI:
    def __init__(
        self,
        conf: str,
        headless: bool = True,
        config_file: str = CONFIG_FILE,
        save_pages: bool = False,
    ):
        """Initializes the OpenReviewAPI.

        Args:
        conf (str): Name of the conference.
        headless (bool): Run without opening a browser window if True.
        config_file (str): Path to configuration file.
        """
        # Load configuration
        self.config_loader = ConfigLoader(config_file)
        self.conf_config = self.config_loader.get_config(conf)
        self.conf = conf
        self.save_pages = save_pages

        browser_config = self.config_loader.browser_config or BrowserConfig()

        logging.info(f"Using configuration for conference: {self.conf}")

        logging.debug(f"Browser configuration: {browser_config}")

        service = Service()
        options = webdriver.FirefoxOptions()

        if browser_config.geckodriver_path:
            service = Service(browser_config.geckodriver_path)

        if browser_config.firefox_binary:
            logging.debug(f"Using Firefox binary at: {browser_config.firefox_binary}")
            options.binary_location = browser_config.firefox_binary

        if browser_config.window_size:
            options.add_argument(f"--width={browser_config.window_size[0]}")
            options.add_argument(f"--height={browser_config.window_size[1]}")

        if browser_config.additional_args:
            for arg in browser_config.additional_args:
                options.add_argument(arg)

        if headless:
            options.add_argument("--headless")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        self.driver = webdriver.Firefox(options=options, service=service)

        self._login(self.conf_config.url)

    def __del__(self) -> None:
        if hasattr(self, "driver"):
            self.driver.quit()

    def _save_page(self, filename: str) -> None:
        """Generic function to save current page HTML."""
        if not self.save_pages:
            return

        if not hasattr(self, "timestamp_dir"):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.timestamp_dir = f"saved_pages/{timestamp}"

        os.makedirs(self.timestamp_dir, exist_ok=True)
        filepath = f"{self.timestamp_dir}/{filename}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.driver.page_source)

    def _login(self, url: str) -> None:
        # Load username and password.
        load_dotenv()
        username = os.environ["LOGIN"]
        password = os.environ["PASSWORD"]

        # Log in and navigate to url.
        print(f"Opening {url}")
        self.driver.get(url)
        print("Waiting for login page to load...")
        while True:
            try:
                self.driver.find_element(By.ID, "email-input")
                break
            except Exception:
                logging.exception("Waiting for login page to load...")
                pass
        self.driver.find_element(By.ID, "email-input").send_keys(username)
        self.driver.find_element(By.ID, "password-input").send_keys(password)
        self.driver.find_element(By.CLASS_NAME, "btn-login").click()
        print("Logging in.")

        # Wait for page to load, get urls to all papers.
        print("Waiting for page to finish loading...")

        def load_landing_page(driver: webdriver.Firefox) -> list[str | None]:
            while True:
                elements = driver.find_elements(By.XPATH, "//div[@class='note']/h4/a")
                urls = [
                    url.get_attribute("href")
                    for url in elements
                    if url.get_attribute("href") is not None
                ]
                if urls:
                    break
            print("Logged in.")
            print(f"Found {len(urls)} submissions.")
            return urls

        urls = run_with_timeout(
            load_landing_page,
            (self.driver,),
            timeout_duration=TIMEOUT_DURATION,
            default_output=[],
        )
        self.paper_urls = urls

        self._save_page("landing_page.html")

    def _parse_rating(self) -> tuple[list[int], list[int], list[int]]:
        """Parse ratings from reviews using configuration."""
        ratings: list[int] = []
        final_ratings: list[int] = []
        confidences: list[int] = []

        reviews = self.driver.find_element(By.ID, "forum-replies").find_elements(
            By.CLASS_NAME, "depth-odd"
        )

        for reply in reviews:
            content = reply.text

            rating = TextExtractor.extract_value(
                content, self.conf_config.rating_config
            )
            confidence = TextExtractor.extract_value(
                content, self.conf_config.confidence_config
            )
            final_rating = TextExtractor.extract_value(
                content, self.conf_config.final_rating_config
            )

            # Weird workaround to allow any ordering / missing values.
            for value, target_list in [
                (rating, ratings),
                (confidence, confidences),
                (final_rating, final_ratings),
            ]:
                if value is not None:
                    target_list.append(value)

        return ratings, confidences, final_ratings

    def load_submission(self, url: str, skip_reviews: bool = False) -> Submission:
        """Navigate to submission link and parse info.

        Args:
        url (str): URL to submission.
        skip_reviews (bool): Skip looking for reviews and ratings?

        Returns:
        Instance of Submission().
        """

        # Open url.
        self.driver.get(url)

        # Get submission title and ID.
        title = self.driver.find_element(By.CLASS_NAME, "citation_title").text
        content = self.driver.find_element(
            By.XPATH, "//div[@class='forum-note']/div[@class='note-content']"
        ).text
        sub_id = content.split("Number:")[1].strip()

        logging.info(f"Loaded submission: {sub_id} - {title}")

        safe_title = re.sub(r'[<>:"/\\\\|?*]', "_", title)[:50]
        self._save_page(f"{sub_id}_{safe_title}.html")

        # Get replies.
        if skip_reviews:
            ratings, confidences, final_ratings = [], [], []
        else:
            ratings, confidences, final_ratings = run_with_timeout(
                self._parse_rating,
                timeout_duration=TIMEOUT_DURATION,
                default_output=([], [], []),
            )

        return Submission(title, sub_id, ratings, confidences, final_ratings)

    def load_all_submissions(self, skip_reviews: bool = False) -> list[Submission]:
        """Get all submission info."""
        subs = [
            self.load_submission(paper_url, skip_reviews)
            for paper_url in tqdm(self.paper_urls)
        ]
        return subs


def print_csv(subs: list[Submission]) -> None:
    """Print as CSV with all fields matching the rich table."""
    # CSV header
    header = "#,ID,Title,Ratings,Avg,Std,Confidences,Final Ratings,Final Avg,Final Std"
    print(header)

    # CSV rows
    for idx, sub in enumerate(subs):
        row = (
            f"{idx + 1},"
            f"{sub.sub_id},"
            f'"{sub.title}",'  # Quote title in case it contains commas
            f'"{int_list_to_str(sub.ratings)}",'
            f"{mean(sub.ratings)},"
            f"{std(sub.ratings)},"
            f'"{int_list_to_str(sub.confidences)}",'
            f'"{int_list_to_str(sub.final_ratings)}",'
            f"{mean(sub.final_ratings)},"
            f"{std(sub.final_ratings)}"
        )
        print(row)


def save_csv(subs: list[Submission], filename: str = "submissions.csv") -> None:
    """Save submissions as CSV file with all fields matching the rich table."""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        header = (
            "#,ID,Title,Ratings,Avg,Std,Confidences,Final Ratings,Final Avg,Final Std"
        )
        f.write(header + "\n")

        for idx, sub in enumerate(subs):
            row = (
                f"{idx + 1},"
                f"{sub.sub_id},"
                f'"{sub.title}",'
                f'"{int_list_to_str(sub.ratings)}",'
                f"{mean(sub.ratings)},"
                f"{std(sub.ratings)},"
                f'"{int_list_to_str(sub.confidences)}",'
                f'"{int_list_to_str(sub.final_ratings)}",'
                f"{mean(sub.final_ratings)},"
                f"{std(sub.final_ratings)}"
            )
            f.write(row + "\n")

    print(f"CSV saved to {filename}")


def print_rich(subs: list[Submission]) -> None:
    """Pretty print table."""

    console = Console()

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right")
    table.add_column("ID", justify="right")
    table.add_column("Title", justify="left")
    table.add_column("Ratings", justify="right")
    table.add_column("Avg.", justify="right")
    table.add_column("Std.", justify="right")
    table.add_column("Confidences", justify="right")
    table.add_column("Final Ratings", justify="right")
    table.add_column("Avg.", justify="right")
    table.add_column("Std.", justify="right")

    for idx, sub in enumerate(subs):
        table.add_row(
            f"{idx + 1}",
            sub.sub_id,
            sub.title,
            int_list_to_str(sub.ratings),
            mean(sub.ratings),
            std(sub.ratings),
            int_list_to_str(sub.confidences),
            int_list_to_str(sub.final_ratings),
            mean(sub.final_ratings),
            std(sub.final_ratings),
        )

    console.print(table)


def parse_args() -> argparse.Namespace:
    # Load available conferences from config
    try:
        config_loader = ConfigLoader()
        available_confs = config_loader.list_conferences()
    except FileNotFoundError:
        print(f"Warning: {CONFIG_FILE} not found. Using default conferences.")
        available_confs = ["iclr_2025", "cvpr_2025"]

    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="Run in headless mode?")
    parser.add_argument(
        "--skip_reviews",
        action="store_true",
        help="Skip reviews? Select if no reviews are in yet.",
    )
    parser.add_argument(
        "--conf",
        type=str,
        default=available_confs[0] if available_confs else "iclr_2025",
        choices=available_confs,
        help=f"Conference to scrape. Available: {', '.join(available_confs)}",
    )
    parser.add_argument("--simulate", action="store_true", help="Simulate the process.")
    parser.add_argument(
        "--config", type=str, default=CONFIG_FILE, help="Path to configuration file"
    )
    parser.add_argument(
        "--list-conferences",
        action="store_true",
        help="List all available conferences and exit",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--save_pages",
        action="store_true",
        help="Save HTML pages of submissions for debugging purposes",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="submissions.csv",
        help="Path to save the CSV file",
    )

    args = parser.parse_args()
    return args


def main() -> None:
    args = parse_args()

    if args.debug:
        setup_logger(debug=True)

    # List conferences if requested
    if args.list_conferences:
        try:
            config_loader = ConfigLoader(args.config)
            conferences = config_loader.list_conferences()
            print("Available conferences:")
            for conf in conferences:
                conf_config = config_loader.get_config(conf)
                print(f"  - {conf}: {conf_config.url}")
        except FileNotFoundError:
            print(f"Configuration file {args.config} not found!")
        return

    if args.simulate:
        subs = []
        for _ in range(5):
            ratings = [secrets.choice(range(1, 6)) for _ in range(secrets.randbelow(4))]
            final_ratings = [
                secrets.choice(range(1, 6)) for _ in range(secrets.randbelow(4))
            ]
            subs.append(
                Submission(
                    title="Title " + secrets.choice(string.ascii_uppercase),
                    sub_id=str(secrets.randbelow(19000) + 1000),
                    ratings=ratings,
                    confidences=[
                        secrets.choice(range(1, 5 + 1)) for _ in range(len(ratings))
                    ],
                    final_ratings=final_ratings,
                )
            )

    else:
        obj = ORAPI(
            conf=args.conf,
            headless=args.headless,
            config_file=args.config,
            save_pages=args.save_pages,
        )
        subs = obj.load_all_submissions(args.skip_reviews)

        print_rich(subs)
        save_csv(subs, filename=args.csv)


if __name__ == "__main__":
    main()
