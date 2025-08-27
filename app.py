import os
import requests
from bs4 import BeautifulSoup
import json
from dotenv import load_dotenv
import google.generativeai as genai
import facebook
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# --- Constants and State Management ---
POSTED_ARTICLES_FILE = "posted_articles.txt"
current_key_index = 0

def load_posted_ids():
    if not os.path.exists(POSTED_ARTICLES_FILE):
        return set()
    with open(POSTED_ARTICLES_FILE, 'r') as f:
        return set(line.strip() for line in f if line.strip())

def save_posted_id(article_id):
    with open(POSTED_ARTICLES_FILE, 'a') as f:
        f.write(str(article_id) + "\n")

def translate_and_style_article(article):
    """
    Translates and styles an article, rotating through API keys on quota failure.
    """
    global current_key_index
    headline = article['headline']
    body = article['body']

    keys = [
        os.getenv("GEMINI_API_KEY_1"),
        os.getenv("GEMINI_API_KEY_2"),
        os.getenv("GEMINI_API_KEY_3")
    ]

    valid_keys = [key for key in keys if key]
    if not valid_keys:
        print("Skipping translation: No Gemini API keys found in .env file.")
        return None

    start_index = current_key_index
    for i in range(len(valid_keys)):
        # Start from the current key and loop around
        key_to_try_index = (start_index + i) % len(valid_keys)
        api_key = valid_keys[key_to_try_index]

        try:
            genai.configure(api_key=api_key)
            print(f"Translating \"{headline}\" using API Key #{key_to_try_index + 1}...")

            model = genai.GenerativeModel('gemini-1.5-flash-latest')
            prompt = f"""Act as a friendly and funny Thai football blogger... [PROMPT HIDDEN FOR BREVITY]"""

            response = model.generate_content(prompt)
            cleaned_response_text = response.text.strip().replace("```json", "").replace("```", "")
            styled_content = json.loads(cleaned_response_text)

            print(f"Successfully translated using API Key #{key_to_try_index + 1}.")
            current_key_index = key_to_try_index # Update the index to the key that worked
            return styled_content

        except Exception as e:
            if "429" in str(e) and "quota" in str(e).lower():
                print(f"API Key #{key_to_try_index + 1} has exceeded its quota. Trying next key...")
                continue
            else:
                print(f"An unexpected error occurred with Gemini API Key #{key_to_try_index + 1}: {e}")
                return None

    print("All available Gemini API keys have exceeded their quotas. Skipping translation.")
    current_key_index = len(valid_keys) # Mark all keys as used
    return None

def post_to_facebook(article_data):
    page_id = os.getenv("FACEBOOK_PAGE_ID")
    access_token = os.getenv("FACEBOOK_ACCESS_TOKEN")
    if not page_id or not access_token:
        print("Skipping Facebook post: Credentials not found.")
        return False
    try:
        print(f"Posting to Facebook page: {page_id}")
        graph = facebook.GraphAPI(access_token)
        source_text = article_data.get('source', 'ESPN')
        message = f"{article_data['headline_th']}\n\n{article_data['body_th_styled']}\n\n---\nขอขอบคุณภาพข่าวจาก : {source_text}\nลิงค์ข่าว : {article_data['url']}"
        image_response = requests.get(article_data['image_url'])
        image_response.raise_for_status()
        graph.put_photo(image=image_response.content, message=message, album_path=f'{page_id}/photos')
        print("Successfully posted to Facebook.")
        return True
    except Exception as e:
        print(f"Facebook API Error: {e}")
        return False

def get_article_content(article_url):
    print(f"Scraping article content from: {article_url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(article_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        content_selectors = ['div.article-body', 'div.story-body', 'article']
        article_body = None
        for selector in content_selectors:
            article_body = soup.select_one(selector)
            if article_body:
                break
        if not article_body:
            paragraphs = soup.find('body').find_all('p')
        else:
            paragraphs = article_body.find_all('p')
        content = "\n\n".join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
        return content if content else None
    except Exception as e:
        print(f"Error scraping content from {article_url}: {e}")
        return None

def get_espn_news():
    leagues = {'eng.1': 'Premier League', 'esp.1': 'La Liga', 'ger.1': 'Bundesliga', 'ita.1': 'Serie A'}
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
            for article in api_articles:
                article['source'] = 'ESPN'
                article['league'] = league_name
            all_articles.extend(api_articles)
        except requests.exceptions.RequestException as e:
            print(f"Could not fetch news for {league_name}. Error: {e}")
    return all_articles

def run_full_job():
    global current_key_index
    current_key_index = 0 # Reset to the first key for every new job run
    print(f"\n--- Running scheduled job at {datetime.now()} ---")
    print("API Key index reset to 0.")
    # The configure_gemini() call is no longer needed here, it will be handled by the translation function
    posted_ids = load_posted_ids()
    print(f"Loaded {len(posted_ids)} previously posted article IDs.")
    raw_articles = get_espn_news()
    articles_no_videos = [a for a in raw_articles if a.get('type') != 'Media']
    sorted_articles = sorted(articles_no_videos, key=lambda x: x.get('published', ''), reverse=True)
    print(f"Found {len(sorted_articles)} valid articles to process.")
    new_posts_made = 0
    for article_summary in sorted_articles:
        if new_posts_made >= 5:
            print("Posted 5 new articles. Ending job run.")
            break
        article_id = str(article_summary.get('id'))
        if article_id in posted_ids:
            continue
        print(f"\n--- Processing new article from {article_summary.get('league')}: \"{article_summary.get('headline')}\" ---")
        article_url = article_summary.get('links', {}).get('web', {}).get('href')
        if not article_url:
            continue
        full_content = get_article_content(article_url)
        if not full_content:
            continue
        image_url = (article_summary.get('images', [{}])[0] or {}).get('url')
        final_article = {'id': article_id, 'headline': article_summary.get('headline'), 'url': article_url, 'image_url': image_url, 'body': full_content, 'source': 'ESPN'}
        styled_result = translate_and_style_article(final_article)
        if styled_result:
            styled_result.update(final_article)
            post_successful = post_to_facebook(styled_result)
            if post_successful:
                save_posted_id(article_id)
                new_posts_made += 1
    print("--- Scheduled job finished ---")

if __name__ == '__main__':
    scheduler = BlockingScheduler(timezone="Asia/Bangkok")
    scheduler.add_job(run_full_job, 'cron', hour='1,4,8,12,16,21')
    print("Scheduler started. Press Ctrl+C to exit.")
    try:
        run_full_job()
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")
