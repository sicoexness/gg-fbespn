import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import google.generativeai as genai
import facebook

# Initialize Flask App
app = Flask(__name__)

# --- Database Setup ---
DATABASE_FILE = 'bot_database.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False) # Allow multi-thread access
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, message TEXT NOT NULL)')
    conn.commit()
    conn.close()
    print("Database initialized.")

def get_setting(key):
    conn = get_db_connection()
    setting = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return setting['value'] if setting else None

def set_setting(key, value):
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def add_log(message):
    conn = get_db_connection()
    conn.execute('INSERT INTO logs (message) VALUES (?)', (message,))
    conn.commit()
    conn.close()

def get_logs(limit=100):
    conn = get_db_connection()
    logs = conn.execute('SELECT timestamp, message FROM logs ORDER BY timestamp DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    return logs

# --- Bot Logic ---

POSTED_ARTICLES_FILE = "posted_articles.txt" # We can deprecate this later for a DB solution

def load_posted_ids():
    if not os.path.exists(POSTED_ARTICLES_FILE):
        return set()
    with open(POSTED_ARTICLES_FILE, 'r') as f:
        return set(line.strip() for line in f if line.strip())

def save_posted_id(article_id):
    with open(POSTED_ARTICLES_FILE, 'a') as f:
        f.write(str(article_id) + "\n")

def translate_and_style_article(article):
    headline = article['headline']
    body = article['body']
    gemini_api_key = get_setting("GEMINI_API_KEY")
    if not gemini_api_key:
        add_log("Skipping translation: GEMINI_API_KEY not found in settings.")
        return None
    try:
        genai.configure(api_key=gemini_api_key)
        add_log(f"Translating and styling: \"{headline}\"")
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        prompt = f"""Act as a friendly and funny Thai football blogger. Your goal is to take a news article and make it exciting for Thai football fans.
        Here is the article: Headline: "{headline}" Body: {body}
        Please perform the following tasks:
        1. Translate the entire article (headline and body) into Thai.
        2. Rewrite the translated article in a fun, engaging, and informal style. Use slang and exciting language that a football fan would love.
        3. The final post must be short and punchy, designed to be read in under one minute.
        4. Structure your response as a JSON object with two keys: "headline_th" and "body_th_styled".
        """
        response = model.generate_content(prompt)
        cleaned_response_text = response.text.strip().replace("```json", "").replace("```", "")
        styled_content = json.loads(cleaned_response_text)
        add_log("Successfully translated and styled the article.")
        return styled_content
    except Exception as e:
        add_log(f"An error occurred with the Gemini API: {e}")
        return None

def post_to_facebook(article_data):
    page_id = get_setting("FACEBOOK_PAGE_ID")
    access_token = get_setting("FACEBOOK_ACCESS_TOKEN")
    if not page_id or not access_token:
        add_log("Skipping Facebook post: Credentials not found in settings.")
        return False
    try:
        add_log(f"Posting to Facebook page: {page_id}")
        graph = facebook.GraphAPI(access_token)
        source = article_data.get('source', 'ESPN')
        source_text = 'Yahoo Sport' if source == 'Yahoo' else 'ESPN'
        message = f"{article_data['headline_th']}\n\n{article_data['body_th_styled']}\n\n---\nขอขอบคุณภาพข่าวจาก : {source_text}\nลิงค์ข่าว : {article_data['url']}"
        image_response = requests.get(article_data['image_url'])
        image_response.raise_for_status()
        graph.put_photo(image=image_response.content, message=message, album_path=f'{page_id}/photos')
        add_log("Successfully posted to Facebook.")
        return True
    except Exception as e:
        add_log(f"Facebook API Error: {e}")
        return False

def get_article_content(article_url):
    add_log(f"Scraping article content from: {article_url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(article_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        content_selectors = ['div.article-body', 'div.story-body', 'div.article__body', 'article']
        article_body = None
        for selector in content_selectors:
            article_body = soup.select_one(selector)
            if article_body:
                add_log(f"Found content with selector: '{selector}'")
                break
        if not article_body:
            add_log("Warning: Could not find a specific article body container. Falling back to all <p> tags.")
            paragraphs = soup.find('body').find_all('p')
        else:
            paragraphs = article_body.find_all('p')
        content = "\n\n".join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
        if not content:
            add_log("Warning: Scraped content is empty.")
            return None
        return content
    except Exception as e:
        add_log(f"Error scraping content from {article_url}: {e}")
        return None

def get_espn_news():
    leagues = {'eng.1': 'Premier League', 'esp.1': 'La Liga', 'ger.1': 'Bundesliga', 'ita.1': 'Serie A'}
    all_articles = []
    add_log("Fetching news from ESPN API for all specified leagues...")
    for league_code, league_name in leagues.items():
        api_url = f"http://site.api.espn.com/apis/site/v2/sports/soccer/{league_code}/news"
        try:
            response = requests.get(api_url)
            response.raise_for_status()
            data = response.json()
            api_articles = data.get('articles', [])
            add_log(f"Found {len(api_articles)} articles for {league_name}.")
            for article in api_articles:
                article['source'] = 'ESPN'
                article['league'] = league_name
            all_articles.extend(api_articles)
        except requests.exceptions.RequestException as e:
            add_log(f"Could not fetch news for {league_name}. Error: {e}")
            continue
    add_log(f"Found a total of {len(all_articles)} articles from all ESPN leagues.")
    return all_articles

def run_full_job():
    add_log("--- Running scheduled job ---")
    posted_ids = load_posted_ids()
    add_log(f"Loaded {len(posted_ids)} previously posted article IDs.")
    raw_articles = get_espn_news()
    articles_no_videos = [a for a in raw_articles if a.get('type') != 'Media']
    sorted_articles = sorted(articles_no_videos, key=lambda x: x.get('published', ''), reverse=True)
    add_log(f"Found {len(sorted_articles)} valid articles to process. Now checking for duplicates.")
    new_posts_made = 0
    for article_summary in sorted_articles:
        if new_posts_made >= 5:
            add_log("Successfully posted 5 new articles. Ending job run.")
            break
        article_id = str(article_summary.get('id'))
        if article_id in posted_ids:
            continue
        add_log(f"Found new article to process from {article_summary.get('league')}: \"{article_summary.get('headline')}\"")
        article_url = article_summary.get('links', {}).get('web', {}).get('href')
        if not article_url:
            add_log("Skipping article due to missing URL.")
            continue
        full_content = get_article_content(article_url)
        if not full_content:
            add_log(f"Skipping article because no content could be scraped from URL: {article_url}")
            continue
        image_url = None
        images = article_summary.get('images', [])
        if images:
            image_url = images[0].get('url')
        final_article = {
            'id': article_id, 'headline': article_summary.get('headline'), 'url': article_url,
            'image_url': image_url, 'body': full_content, 'source': article_summary.get('source')
        }
        styled_result = translate_and_style_article(final_article)
        if styled_result and styled_result.get('headline_th') != final_article.get('headline'):
            styled_result['image_url'] = final_article['image_url']
            styled_result['url'] = final_article['url']
            styled_result['source'] = final_article['source']
            post_successful = post_to_facebook(styled_result)
            if post_successful:
                save_posted_id(article_id)
                add_log(f"Successfully saved article ID {article_id} to history.")
                new_posts_made += 1
        else:
            add_log(f"Skipping Facebook post for '{final_article['headline']}' due to translation/styling failure.")
    if new_posts_made == 0:
        add_log("No new articles were found to post in this run.")
    add_log("--- Scheduled job finished ---")

# --- Flask Routes ---
@app.route('/')
def index():
    keys = ['GEMINI_API_KEY', 'FACEBOOK_ACCESS_TOKEN', 'FACEBOOK_PAGE_ID']
    settings = {key: get_setting(key) for key in keys}
    logs = get_logs(limit=50)
    return render_template('index.html', settings=settings, logs=logs)

@app.route('/save_settings', methods=['POST'])
def save_settings():
    keys = ['GEMINI_API_KEY', 'FACEBOOK_ACCESS_TOKEN', 'FACEBOOK_PAGE_ID']
    for key in keys:
        # The form input names are lowercase and with underscores
        set_setting(key, request.form.get(key.lower()))
    add_log("API settings have been updated.")
    return redirect(url_for('index'))

@app.route('/trigger_job', methods=['POST'])
def trigger_job():
    """Triggers a manual run of the bot job."""
    add_log("Manual job run triggered from web UI.")
    scheduler.add_job(run_full_job, 'date') # 'date' trigger runs the job immediately
    return redirect(url_for('index'))

# Initialize the database when the app starts
init_db()

# --- Scheduler Setup ---
from apscheduler.schedulers.background import BackgroundScheduler
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(run_full_job, 'cron', hour='1,4,8,12,16,21')
scheduler.start()


if __name__ == '__main__':
    # This is for local development only
    app.run(debug=True, port=5001, use_reloader=False) # use_reloader=False is important for scheduler
