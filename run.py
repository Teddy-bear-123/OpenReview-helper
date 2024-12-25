import argparse
import os
from dataclasses import dataclass

import numpy as np
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from tqdm import tqdm


@dataclass
class Submission:
    """Class containing submission details."""
    title: str  # Title.
    sub_id: str  # Paper ID.
    ratings: list[int]  # List of reviewer ratings.
    confidences: list[int]  # List of reviewer confidences.

    def __repr__(self) -> str:
        ratings = [str(item) for item in self.ratings]
        ratings = ", ".join(ratings)
        return f"{self.sub_id}, {self.title}, {ratings}"

    def info(self) -> str:
        return f"ID: {self.sub_id}, {self.title}, " + \
            f"Ratings: {self.ratings}, " + \
            f"Avg: {np.mean(self.ratings):.2f}, " + \
            f"Var: {np.var(self.ratings):.2f}"


class ORAPI:
    conf_to_url = {
        "iclr_2025": "https://openreview.net/group?id=ICLR.cc/2025/Conference/Area_Chairs",
        "cvpr_2025": "https://openreview.net/group?id=thecvf.com/CVPR/2025/Conference/Area_Chairs",
        # Add new ones here.
    }

    def __init__(self, conf: str, headless: bool = True):
        """Initializes the OpenReviewAPI.

        Args:
        conf (str): Name of the conference.
        headless (bool): Run without opening a browser window if True.
        skip_reviews (bool): Don't look for paper reviews if True.
        """
        # Create webdriver.
        options = webdriver.FirefoxOptions()
        if headless:
            options.add_argument("--headless")
        self.driver = webdriver.Firefox(options=options)

        self._login(self._get_url(conf))

    def __del__(self):
        self.driver.quit()

    def _get_url(self, conf: str) -> str:
        """Get conference Area Chair URL."""
        if conf in self.conf_to_url:
            return self.conf_to_url[conf]
        else:
            raise ValueError(f"Conf: {conf} not supported.")

    def _login(self, url: str) -> None:
        # Load username and password.
        load_dotenv()
        username = os.environ["USERNAME"]
        password = os.environ["PASSWORD"]

        # Log in and navigate to url.
        print(f"Opening {url}")
        self.driver.get(url)
        self.driver.find_element(By.ID, "email-input").send_keys(username)
        self.driver.find_element(By.ID, "password-input").send_keys(password)
        self.driver.find_element(By.CLASS_NAME, "btn-login").click()
        print("Logging in.")

        # Wait for page to load, get urls to all papers.
        print("Waiting for page to finish loading...")
        while True:
            urls = self.driver.find_elements(By.XPATH, "//div[@class='note']/h4/a")
            urls = [url.get_attribute("href") for url in urls]
            if urls:
                break
        print("Logged in.")
        print(f"Found {len(urls)} submissions.")
        self.paper_urls = urls

    def load_submission(self, url: str, skip_reviews: bool = False) -> Submission:
        """Navigate to submission link and parse info.

        Args:
        driver: Instance of Firefox WebDriver.
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
            By.XPATH, "//div[@class='forum-note']/div[@class='note-content']").text
        sub_id = content.split("Number:")[1].strip()

        # Get replies.
        if skip_reviews:
            replies = []
        else:
            while True:
                # Keep trying until page loads...
                replies = self.driver.find_element(
                    By.ID, "forum-replies").find_elements(By.CLASS_NAME, "depth-odd")
                if replies:
                    break

        # Get ratings and confidences from each valid rating.
        ratings, confidences = [], []
        for reply in replies:
            content = reply.text
            rating_start = content.find("Rating: ")
            if rating_start > 0:
                confidence_start = content.find("Confidence: ")
                code_start = content.find("Code Of Conduct: ")
                rating = int(
                    content[rating_start:confidence_start].split(":")[1].strip())
                confidence = int(
                    content[confidence_start:code_start].split(":")[1].strip())
                ratings.append(rating)
                confidences.append(confidence)

        return Submission(title, sub_id, ratings, confidences)

    def load_all_submissions(self, skip_reviews: bool = False):
        """Get all submission info."""
        subs = [self.load_submission(paper_url, skip_reviews) for paper_url in tqdm(self.paper_urls)]
        return subs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true",
                        help="Run in headless mode?")
    parser.add_argument("--skip_reviews", action="store_true",
                        help="Skip reviews? Select if no reviews are in yet.")
    parser.add_argument("--conf", type=str,
                        default="iclr_2025", choices=list(ORAPI.conf_to_url.keys()))
    args = parser.parse_args()
    return args


def main() -> None:
    args = parse_args()

    # Initialize API object and get all info.
    obj = ORAPI(conf=args.conf, headless=args.headless)
    subs = obj.load_all_submissions(args.skip_reviews)

    # Print info.
    for idx, sub in enumerate(subs):
        print(f"{idx + 1}, {sub}")


if __name__ == "__main__":
    main()
