import argparse
import os
from dataclasses import dataclass

import numpy as np
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By


CONF_TO_URL_MAPPING = {
    "iclr_2025": "https://openreview.net/group?id=ICLR.cc/2025/Conference/Area_Chairs",
    "cvpr_2025": "https://openreview.net/group?id=thecvf.com/CVPR/2025/Conference/Area_Chairs",
    # Add new ones here.
}


@dataclass
class Submission:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true",
                        help="Run in headless mode?")
    parser.add_argument("--skip_reviews", action="store_true",
                        help="Skip reviews? Select if no reviews are in yet.")
    parser.add_argument("--conf", type=str,
                        default="iclr_2025", choices=list(CONF_TO_URL_MAPPING.keys()))
    args = parser.parse_args()

    # Add url.
    args.url = CONF_TO_URL_MAPPING[args.conf]

    # Load username and password.
    load_dotenv()
    args.username = os.environ["USERNAME"]
    args.password = os.environ["PASSWORD"]

    return args


def get_paper_info(driver, url: str, skip_reviews: bool = False) -> Submission:
    """Navigate to submission link and parse info.

    Args:
    driver: Instance of Firefox WebDriver.
    url (str): URL to submission.
    skip_reviews (bool): Skip looking for reviews and ratings?

    Returns:
    Instance of Submission().    
    """

    # Open url.
    driver.get(url)

    # Get submission title and ID.
    title = driver.find_element(By.CLASS_NAME, "citation_title").text
    content = driver.find_element(
        By.XPATH, "//div[@class='forum-note']/div[@class='note-content']").text
    sub_id = content.split("Number:")[1].strip()

    # Get replies.
    if skip_reviews:
        replies = []
    else:
        while True:
            replies = driver.find_element(
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


def main(args: argparse.Namespace) -> None:
    # Create driver.
    options = webdriver.FirefoxOptions()
    if args.headless:
        options.add_argument("--headless")
    driver = webdriver.Firefox(options=options)

    # Log in and navigate to url.
    print("Logging in.")
    print(f"Opening {args.url}")
    driver.get(args.url)
    driver.find_element(By.ID, "email-input").send_keys(args.username)
    driver.find_element(By.ID, "password-input").send_keys(args.password)
    driver.find_element(By.CLASS_NAME, "btn-login").click()
    print("Logged in.")

    # Wait for page to load, get urls to all papers.
    while True:
        urls = driver.find_elements(By.XPATH, "//div[@class='note']/h4/a")
        urls = [url.get_attribute("href") for url in urls]
        if urls:
            break
    print(f"Found {len(urls)} submissions.")

    # Visit each url.
    for idx, url in enumerate(urls):
        print(f"{idx + 1}, {get_paper_info(driver, url, args.skip_reviews)}")

    driver.quit()


if __name__ == "__main__":
    main(parse_args())
