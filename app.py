from flask import Flask, render_template, request, send_file
import requests
from bs4 import BeautifulSoup
import re
import json
from html import unescape
import time
import random
import os
import io
import csv

app = Flask(__name__)

user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
    'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36',
]

def extract_needed_data(json_data):
    if isinstance(json_data, str):
        json_data = json.loads(json_data)

    pages = json_data.get("pages", {})
    current_page = pages.get('current', {})
    resId = str(current_page.get("resId", ""))

    restaurant_data = pages.get('restaurant', {}).get(resId, {})
    name = restaurant_data.get("sections", {}).get("SECTION_BASIC_INFO", {}).get('name', 'Restaurant')

    menus = restaurant_data.get("order", {}).get("menuList", {}).get("menus", [])

    filtered_data = []
    for menu in menus:
        category_name = menu.get("menu", {}).get("name", "")
        for category in menu.get("menu", {}).get("categories", []):
            sub_category_name = category.get("category", {}).get("name", "")
            for item in category.get("category", {}).get("items", []):
                item_data = item.get("item", {})
                filtered_data.append({
                    "restaurant": name,
                    "category": category_name,
                    "sub_category": sub_category_name,
                    "dietary_slugs": ','.join(item_data.get("dietary_slugs", [])),
                    "item_name": item_data.get("name", ""),
                    "price": item_data.get("display_price", ""),
                    "desc": item_data.get("desc", "")
                })

    return filtered_data, name

def get_menu(url, retries=3):
    if not url.endswith('/order'):
        url += '/order'

    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'https://www.google.com/',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    time.sleep(random.uniform(2.5, 5.0))

    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            break
        except requests.RequestException as e:
            wait = (2 ** attempt) + random.uniform(0.5, 1.5)
            print(f"Retry {attempt + 1}/{retries} failed: {e}. Retrying in {wait:.1f}s.")
            time.sleep(wait)
    else:
        return None, None, "Failed to fetch the page after multiple attempts."

    soup = BeautifulSoup(response.text, 'html.parser')

    scripts = soup.find_all('script')
    for script in scripts:
        if 'window.__PRELOADED_STATE__' in script.text:
            match = re.search(r'window\.__PRELOADED_STATE__ = JSON\.parse\((.+?)\);', script.text)
            if match:
                try:
                    escaped_json = match.group(1)
                    decoded_json_str = unescape(escaped_json)
                    parsed_json = json.loads(decoded_json_str)
                    preloaded_state = json.loads(parsed_json)

                    menu_data, restaurant_name = extract_needed_data(preloaded_state)
                    return menu_data, restaurant_name, None
                except Exception as e:
                    return None, None, f"Error parsing embedded JSON: {e}"

    return None, None, "No embedded menu data found on this page."

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    menu_items = None
    restaurant_name = None

    if request.method == "POST":
        url = request.form.get("url", "").strip()
        if not url:
            error = "Please enter a valid Zomato restaurant URL."
        else:
            menu_items, restaurant_name, error = get_menu(url)

    return render_template("index.html", error=error, menu_items=menu_items, restaurant_name=restaurant_name)

@app.route("/download_csv", methods=["POST"])
def download_csv():
    data = request.form.get("csv_data")
    restaurant_name = request.form.get("restaurant_name", "menu")

    # Sanitize restaurant name for filename
    restaurant_name = re.sub(r'[^\w\s-]', '', restaurant_name).strip().replace(' ', '_')

    if not data:
        return "No data to download", 400

    menu_items = json.loads(data)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["restaurant", "category", "sub_category", "item_name", "price", "desc", "dietary_slugs"])
    writer.writeheader()
    for item in menu_items:
        writer.writerow(item)

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"{restaurant_name}_menu.csv"
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
