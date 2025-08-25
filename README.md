# ESPN Football News Scraper & Facebook Poster

This project is an automated bot that scrapes football news from ESPN, translates it into Thai with a fun and engaging style using the Gemini API, and automatically posts it to a Facebook Page.

## Features

-   **Web Scraping**: Fetches the latest 5 news articles from the English Premier League section of ESPN.
-   **Video Filtering**: Intelligently skips any news items that are videos.
-   **AI Translation & Styling**: Uses Google's Gemini API to:
    1.  Translate articles from English to Thai.
    2.  Rewrite the content in a fun, informal, and engaging tone perfect for social media.
-   **Facebook Automation**: Posts the styled headline, body, and the original article image directly to a specified Facebook Page.
-   **Scheduling**: Runs automatically at 8:00 AM, 12:00 PM, and 4:00 PM (Bangkok time) every day.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Environment Variables

This project requires API keys and credentials to function. Create a file named `.env` in the root directory and add the following variables. You can use the `.env.example` file as a template.

```
# Get from Google AI Studio (https://aistudio.google.com/app/apikey)
GEMINI_API_KEY="YOUR_GEMINI_API_KEY"

# Get from Meta for Developers dashboard for your app/page
# Requires pages_read_engagement and pages_manage_posts permissions
FACEBOOK_ACCESS_TOKEN="YOUR_FACEBOOK_PAGE_ACCESS_TOKEN"
FACEBOOK_PAGE_ID="YOUR_FACEBOOK_PAGE_ID"
```

## Running Locally

To run the scheduler locally for testing or development, simply run the `app.py` script from your terminal:

```bash
python app.py
```

The script will run one job immediately and then start the schedule. Press `Ctrl+C` to stop the scheduler.

## Deployment on Render.com

This project is ready to be deployed to [Render.com](https://render.com/).

1.  **Push to GitHub:** Create a new repository on GitHub and push your project code to it.

2.  **Create a New Service on Render:**
    -   Log in to your Render dashboard.
    -   Click "New +" and select "Background Worker".
    -   Connect your GitHub repository.
    -   Give your service a name.

3.  **Configure the Service:**
    -   **Start Command:** Render will automatically detect the `Procfile` and use `python app.py` as the start command.
    -   **Instance Type:** The free tier is likely sufficient to start.
    -   **Environment Variables:** Under the "Environment" tab, click "Add Environment Variable" or "Add Secret File" to add the three required variables (`GEMINI_API_KEY`, `FACEBOOK_ACCESS_TOKEN`, `FACEBOOK_PAGE_ID`) with their corresponding values. This is the most important step for the deployed application to work.

4.  **Deploy:**
    -   Click "Create Background Worker". Render will automatically pull your code, install dependencies from `requirements.txt`, and start the worker using the `Procfile` command. The scheduler will then be live and will post at the scheduled times.
