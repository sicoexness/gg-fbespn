import os
import requests
from bs4 import BeautifulSoup
import json
from dotenv import load_dotenv
import google.generativeai as genai
import facebook

# Load environment variables from .env file
load_dotenv()

from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime

# --- Constants and Setup ---
POSTED_ARTICLES_FILE = "posted_articles.txt"

def load_posted_ids():
    """Reads the file of posted article IDs and returns them as a set."""
    if not os.path.exists(POSTED_ARTICLES_FILE):
        return set()
    with open(POSTED_ARTICLES_FILE, 'r') as f:
        # Read lines, strip whitespace, and filter out any empty lines
        return set(line.strip() for line in f if line.strip())

def save_posted_id(article_id):
    """Appends a new article ID to the history file."""
    with open(POSTED_ARTICLES_FILE, 'a') as f:
        f.write(str(article_id) + "\n")

# --- Gemini Configuration ---
# Configure the generative AI model
try:
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        print("Warning: GEMINI_API_KEY not found in .env file. Translation/styling will be skipped.")
        # Configure with a dummy key to avoid crashing the app on startup
        genai.configure(api_key="DUMMY_KEY")
    else:
        genai.configure(api_key=gemini_api_key)
except Exception as e:
    print(f"Error configuring Gemini: {e}")


def translate_and_style_article(article):
    """
    Translates and styles a single article using the Gemini API.
    """
    headline = article['headline']
    body = article['body']

    # Do not proceed if the API key is missing or is the dummy key
    if not os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") == "DUMMY_KEY":
        print("Skipping translation and styling due to missing or dummy API key.")
        return {
            'headline_th': headline, # Fallback to English
            'body_th_styled': body # Fallback to English
        }

    try:
        print(f"Translating and styling: \"{headline}\"")
        # Use a specific, up-to-date model name. 'gemini-1.5-flash-latest' is a good choice.
        model = genai.GenerativeModel('gemini-1.5-flash-latest')

        # --- Prompt for Translation and Styling in one go for efficiency ---
        prompt = f"""
        Act as a friendly and funny Thai football blogger. Your goal is to take a news article and make it exciting for Thai football fans.

        Here is the article:
        Headline: "{headline}"
        Body:
        {body}

        Please perform the following tasks:
        1.  Translate the entire article (headline and body) into Thai.
        2.  Rewrite the translated article in a fun, engaging, and informal style. Use slang and exciting language that a football fan would love.
        3.  The final post must be short and punchy, designed to be read in under one minute.
        4.  Structure your response as a JSON object with two keys: "headline_th" and "body_th_styled".

        Example of a good tone:
        "โอ้โห! ข่าวใหญ่มาแล้ว! ไอ้หนูคนนี้มันจะเทพไปไหนเนี่ย!?"
        "บอกเลยว่างานนี้ แฟนๆ ทีม X มีหนาวๆ ร้อนๆ กันบ้างล่ะ!"

        JSON output format:
        {{
            "headline_th": "Your translated and styled headline here",
            "body_th_styled": "Your fun, engaging, and rewritten Thai body text here."
        }}
        """

        response = model.generate_content(prompt)

        # Clean up the response from Gemini, which might include markdown formatting
        cleaned_response_text = response.text.strip().replace("```json", "").replace("```", "")

        # Parse the JSON string from the response
        styled_content = json.loads(cleaned_response_text)

        print("Successfully translated and styled the article.")
        return styled_content

    except Exception as e:
        print(f"An error occurred with the Gemini API: {e}")
        # Return a default, un-styled version on error
        return {
            'headline_th': headline, # Fallback to English
            'body_th_styled': body # Fallback to English
        }


def post_to_facebook(article_data):
    """
    Posts a single article to a Facebook Page.
    article_data should be a dictionary with 'headline_th', 'body_th_styled', and 'image_url'.
    """
    page_id = os.getenv("FACEBOOK_PAGE_ID")
    access_token = os.getenv("FACEBOOK_ACCESS_TOKEN")

    if not page_id or not access_token:
        print("Warning: FACEBOOK_PAGE_ID or FACEBOOK_ACCESS_TOKEN not found in .env file. Skipping Facebook post.")
        return False

    try:
        print(f"Posting to Facebook page: {page_id}")
        graph = facebook.GraphAPI(access_token)

        # Determine the source for attribution
        source = article_data.get('source', 'ESPN') # Default to ESPN
        if source == 'Yahoo':
            source_text = 'Yahoo Sport'
        else:
            source_text = 'ESPN'

        # Combine headline and body for the post message, and add the attribution
        message = f"""{article_data['headline_th']}

{article_data['body_th_styled']}

---
ขอขอบคุณภาพข่าวจาก : {source_text}
ลิงค์ข่าว : {article_data['url']}"""

        # The image_url is the URL of the image we scraped from ESPN
        # We need to download the image content first to upload it
        image_response = requests.get(article_data['image_url'])
        image_response.raise_for_status()

        # Use put_photo to post an image with a caption
        graph.put_photo(image=image_response.content, message=message, album_path=f'{page_id}/photos')

        print("Successfully posted to Facebook.")
        return True

    except facebook.GraphAPIError as e:
        print(f"Facebook API Error: {e}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Error downloading image for Facebook post: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during Facebook posting: {e}")
        return False


def get_article_content(article_url):
    """
    Scrapes the full content of a single ESPN article page.
    """
    try:
        print(f"Scraping article content from: {article_url}")
        # Using a common browser user-agent is good practice
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(article_url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # --- Selector Logic ---
        # Let's try to find the article body with a few common selectors.
        # ESPN articles often use a class like 'article__body'.
        content_selectors = [
            'div.article-body',
            'div.story-body',
            'div.article__body',
            'article' # The <article> tag itself is a good candidate
        ]

        article_body = None
        for selector in content_selectors:
            article_body = soup.select_one(selector)
            if article_body:
                print(f"Found content with selector: '{selector}'")
                break

        if not article_body:
            print("Warning: Could not find a specific article body container. Falling back to all <p> tags.")
            # As a fallback, just get all paragraphs from the body tag
            paragraphs = soup.find('body').find_all('p')
        else:
            paragraphs = article_body.find_all('p')

        # Join the text from all found paragraphs
        content = "\n\n".join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])

        if not content:
            print("Warning: Scraped content is empty. The selectors might be wrong or page structure has changed.")
            return None

        return content

    except requests.exceptions.RequestException as e:
        print(f"Error scraping article content from {article_url}: {e}")
        return None


def run_full_job():
    """
    This is the main job that will be scheduled.
    It scrapes news from multiple leagues, gets the 5 newest unique articles,
    translates/styles them, and posts them to Facebook.
    """
    print(f"--- Running scheduled job at {datetime.now()} ---")

    # Check for credentials
    if not all([os.getenv("GEMINI_API_KEY"), os.getenv("FACEBOOK_ACCESS_TOKEN"), os.getenv("FACEBOOK_PAGE_ID")]):
        print("Job aborted: Missing one or more API keys.")
        return

    # 1. Load history of posted articles
    posted_ids = load_posted_ids()
    print(f"Loaded {len(posted_ids)} previously posted article IDs from '{POSTED_ARTICLES_FILE}'.")

    # 2. Fetch raw article data from all sources
    raw_articles = get_espn_news()

    # 3. Filter out videos and sort by newest first
    articles_no_videos = [a for a in raw_articles if a.get('type') != 'Media']

    # The 'published' field is a string like "2025-08-25T21:15:26Z"
    # We can sort directly on this string.
    sorted_articles = sorted(articles_no_videos, key=lambda x: x.get('published', ''), reverse=True)

    print(f"Found {len(sorted_articles)} valid articles to process. Now checking for duplicates.")

    new_posts_made = 0
    for article_summary in sorted_articles:
        # Stop after posting 5 new articles
        if new_posts_made >= 5:
            print("Successfully posted 5 new articles. Ending job run.")
            break

        # 4. Check for duplicates
        article_id = str(article_summary.get('id'))
        if article_id in posted_ids:
            # This is expected for most articles, so we don't print every time
            # print(f"Skipping duplicate article: \"{article_summary.get('headline')}\"")
            continue

        print(f"\n--- Found new article to process from {article_summary.get('league')}: \"{article_summary.get('headline')}\" ---")

        # 5. Scrape full content for the new article
        article_url = article_summary.get('links', {}).get('web', {}).get('href')
        if not article_url:
            print("Skipping article due to missing URL.")
            continue

        full_content = get_article_content(article_url)
        if not full_content:
            print(f"Skipping article because no content could be scraped from URL: {article_url}")
            continue

        # 6. Prepare the final article object for processing
        image_url = None
        images = article_summary.get('images', [])
        if images:
            image_url = images[0].get('url')

        final_article = {
            'id': article_id,
            'headline': article_summary.get('headline'),
            'url': article_url,
            'image_url': image_url,
            'body': full_content,
            'source': article_summary.get('source') # Pass the source for attribution
        }

        # 7. Translate and style
        styled_result = translate_and_style_article(final_article)

        # 8. Post to Facebook
        if styled_result and styled_result.get('headline_th') != final_article.get('headline'):
            styled_result['image_url'] = final_article['image_url']
            styled_result['url'] = final_article['url']
            styled_result['source'] = final_article['source']

            post_successful = post_to_facebook(styled_result)

            if post_successful:
                save_posted_id(article_id)
                print(f"Successfully saved article ID {article_id} to history.")
                new_posts_made += 1
        else:
            print(f"Skipping Facebook post for '{final_article['headline']}' due to translation/styling failure.")

    if new_posts_made == 0:
        print("No new articles were found to post in this run.")

    print(f"--- Scheduled job finished at {datetime.now()} ---")


def get_espn_news():
    """
    Fetches news articles for multiple leagues from the unofficial ESPN API.
    """
    leagues = {
        'eng.1': 'Premier League',
        'esp.1': 'La Liga',
        'ger.1': 'Bundesliga',
        'ita.1': 'Serie A'
    }
    all_articles = []

    print("Fetching news from ESPN API for all specified leagues...")
    for league_code, league_name in leagues.items():
        api_url = f"http://site.api.espn.com/apis/site/v2/sports/soccer/{league_code}/news"
        try:
            response = requests.get(api_url)
            response.raise_for_status()
            data = response.json()

            api_articles = data.get('articles', [])
            print(f"Found {len(api_articles)} articles for {league_name}.")

            # Add source and league info to each article
            for article in api_articles:
                article['source'] = 'ESPN'
                article['league'] = league_name

            all_articles.extend(api_articles)

        except requests.exceptions.RequestException as e:
            print(f"Could not fetch news for {league_name}. Error: {e}")
            continue # Continue to the next league if one fails

    print(f"Found a total of {len(all_articles)} articles from all ESPN leagues.")
    return all_articles

if __name__ == '__main__':
    # The main execution block is now for scheduling
    scheduler = BlockingScheduler(timezone="Asia/Bangkok") # Use a specific timezone, e.g., for Thailand

    # Schedule the job to run at 1:00, 4:00, 8:00, 12:00, 16:00 and 21:00
    scheduler.add_job(run_full_job, 'cron', hour='1,4,8,12,16,21', minute='0')

    print("Scheduler started. The job will run at 1:00, 4:00, 8:00, 12:00, 16:00 and 21:00 (Bangkok time).")
    print("Press Ctrl+C to exit.")

    try:
        # Run the job once immediately on startup for confirmation/testing
        print("Running an initial job on startup...")
        run_full_job()

        # Start the scheduler's main loop
        print("\nScheduler is now running. Waiting for the next scheduled time...")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")
        pass
