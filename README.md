# ESPN Football News Bot with Web Control Panel

This project is an automated bot that scrapes football news from multiple European leagues via the ESPN API, translates it into Thai with a fun and engaging style using the Gemini API, and automatically posts it to a Facebook Page.

This new version includes a full web-based control panel for easy management.

## Features

-   **Multi-League Scraping**: Fetches news from the Premier League, La Liga, Bundesliga, and Serie A.
-   **Content Aggregation**: Combines news from all leagues and posts the 5 absolute latest articles.
-   **Deduplication**: Keeps track of posted articles in `posted_articles.txt` to prevent posting the same news twice.
-   **AI Translation & Styling**: Uses Google's Gemini API for translation and styling.
-   **Facebook Automation**: Posts content to a Facebook Page.
-   **Web Control Panel**: A user interface to:
    -   Configure all API Keys (`Gemini`, `Facebook`).
    -   View a live log of the bot's actions.
    -   Manually trigger the bot to run at any time.
-   **Scheduling**: Runs automatically at 01:00, 04:00, 08:00, 12:00, 16:00, and 21:00 (Bangkok time).

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

## Running Locally

1.  **Run the Flask application:**
    ```bash
    python app.py
    ```
2.  **Open your web browser** and go to `http://127.0.0.1:5001`.
3.  **Configure API Keys:** Use the web form to enter your Gemini and Facebook API keys and Page ID. Click "Save Settings".
4.  **Run the bot:** You can either wait for the next scheduled time or click the "Run Job Manually" button to test it immediately.

## Deployment on Render.com

This project is ready to be deployed to [Render.com](https://render.com/) as a **Web Service**.

1.  **Push to GitHub:** Make sure your latest code is on a GitHub repository.

2.  **Create a New Service on Render:**
    -   Log in to your Render dashboard.
    -   Click "New +" and select **"Web Service"**.
    -   Connect your GitHub repository.
    -   Give your service a name.

3.  **Configure the Service:**
    -   **Environment:** Python
    -   **Start Command:** Render will automatically detect the `Procfile` and use `gunicorn app:app`.
    -   **Instance Type:** The free tier is likely sufficient.

4.  **Deploy:**
    -   Click "Create Web Service".
    -   After the service is deployed, go to the URL provided by Render (e.g., `https://your-app-name.onrender.com`).
    -   Use the web UI to enter and save your API keys for the first time. The bot will then be fully operational.
    -   **Note:** Render's free tier web services will "spin down" after a period of inactivity. They will spin up again on the next HTTP request. This means the scheduler might not run reliably on the free tier if the app is inactive. For guaranteed execution, you may need a paid plan or use Render's "Background Worker" or "Cron Job" services for the scheduler part, which is a more advanced setup.
