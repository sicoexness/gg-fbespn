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

        # Combine headline and body for the post message, and add the attribution
        message = f"""{article_data['headline_th']}

{article_data['body_th_styled']}

---
ขอขอบคุณภาพข่าวจาก : ESPN
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
    It scrapes 5 articles, translates/styles them, and posts them to Facebook.
    """
    print(f"--- Running scheduled job at {datetime.now()} ---")

    # Check for credentials at the start of the job
    gemini_key = os.getenv("GEMINI_API_KEY")
    fb_token = os.getenv("FACEBOOK_ACCESS_TOKEN")
    fb_page_id = os.getenv("FACEBOOK_PAGE_ID")

    if not all([gemini_key, fb_token, fb_page_id]) or gemini_key == "DUMMY_KEY":
        print("Job aborted: Missing one or more API keys (GEMINI, FACEBOOK_TOKEN, FACEBOOK_PAGE_ID).")
        return

    articles_to_process = get_espn_news() # This function already gets up to 5

    if not articles_to_process:
        print("No articles found to process. Job finished.")
        return

    print(f"Processing {len(articles_to_process)} articles...")
    for article in articles_to_process:
        print(f"\n--- Processing article: {article['headline']} ---")
        styled_result = translate_and_style_article(article)

        # Check if translation was successful before posting
        if styled_result and styled_result.get('headline_th') != article.get('headline'):
            # Add the image_url and original article url for the posting function
            styled_result['image_url'] = article['image_url']
            styled_result['url'] = article['url']
            post_to_facebook(styled_result)
        else:
            print(f"Skipping Facebook post for '{article['headline']}' due to translation/styling failure.")

    print(f"--- Scheduled job finished at {datetime.now()} ---")


def get_espn_news():
    """
    Fetches news articles from the unofficial ESPN API, filters out videos,
    and scrapes the full content of each article.
    """
    api_url = "http://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/news?limit=15" # Fetch more to ensure we get 5 non-videos
    scraped_articles = []

    print("Fetching news list from ESPN API...")
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()

        api_articles = data.get('articles', [])
        print(f"Found {len(api_articles)} items from API.")

        for article in api_articles:
            if len(scraped_articles) >= 5:
                print("Collected 5 articles. Stopping.")
                break

            if article.get('type') == 'Media':
                print(f"Skipping media item: \"{article.get('headline')}\"")
                continue

            headline = article.get('headline')
            description = article.get('description')
            article_url = article.get('links', {}).get('web', {}).get('href')

            image_url = None
            images = article.get('images', [])
            if images:
                image_url = images[0].get('url')

            if not all([headline, article_url, image_url]):
                print(f"Skipping article \"{headline}\" due to missing data.")
                continue

            full_content = get_article_content(article_url)

            if not full_content:
                print(f"Skipping article \"{headline}\" because no content could be scraped.")
                continue

            scraped_articles.append({
                'headline': headline,
                'url': article_url,
                'image_url': image_url,
                'body': full_content
            })
            print(f"Successfully scraped: \"{headline}\"")

        print(f"\nSuccessfully scraped {len(scraped_articles)} complete articles.")
        return scraped_articles

    except requests.exceptions.RequestException as e:
        print(f"Error fetching news from ESPN API: {e}")
        return []

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
