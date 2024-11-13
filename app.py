import asyncio
import datetime  # Added for date parsing and formatting
from flask import Flask, render_template, request, send_file
from bs4 import BeautifulSoup
import pandas as pd
import nest_asyncio
import random
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import re
import time
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from transformers import BartForConditionalGeneration, BartTokenizer
import torch
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import webbrowser
import threading
import os

# Apply nested asyncio loop patch
nest_asyncio.apply()

# Initialize Flask app
app = Flask(__name__)

# Load BART model and tokenizer for summarization
bart_model = BartForConditionalGeneration.from_pretrained('facebook/bart-large-cnn')
bart_tokenizer = BartTokenizer.from_pretrained('facebook/bart-large-cnn')

# Initialize VADER sentiment analyzer
analyzer = SentimentIntensityAnalyzer()

# Extend VADER Lexicon for aspect-based analysis
aspect_sentiment_keywords = {
    "effective": 2.0, "works well": 2.0, "helped with": 1.5, "relieved": 1.5, "improvement": 1.2, 
    "no effect": -1.5, "ineffective": -2.0, "adverse reaction": -2.0, "nausea": -1.5, "headache": -1.5, 
    "dizziness": -1.2, "allergic reaction": -2.0, "pleasant taste": 1.2, "tastes good": 1.2, "bad taste": -1.5, 
    "tastes awful": -2.0, "strong odor": -1.2, "worth the money": 1.5, "good value": 1.2, "overpriced": -1.5, 
    "too expensive": -2.0, "waste of money": -2.0
}

for word, score in aspect_sentiment_keywords.items():
    analyzer.lexicon[word] = score

# User agents list for rotation to avoid detection
USER_AGENTS = [
    # (Your list of user agents)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/89.0",
    # Add more user agents if needed
]

# Function to get a random user agent
def get_random_user_agent():
    return random.choice(USER_AGENTS)

def create_driver():
    # Correct indentation
    chrome_options = Options()  # No extra space here
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(f"user-agent={get_random_user_agent()}")

    chrome_service = Service(executable_path="C:/mysql/Chromedriver.exe")
    chrome_service = Service(ChromeDriverManager().install())  # This will automatically download the correct driver
    driver = webdriver.Chrome(service=chrome_service, options=chrome_options)

    return driver  # Make sure the return statement is inside the function

# Enhanced function to analyze aspect-specific sentiment with VADER
def analyze_aspect_sentiment_vader(review_text):
    clean_text = re.sub(r'[^\x00-\x7F]+', ' ', review_text)  # Remove non-ASCII characters

    aspect_keywords = {
        "efficacy": ["effective", "works well", "helped with", "relieved", "improvement", "no effect", "ineffective"],
        "side_effects": ["no side effects", "adverse reaction", "nausea", "headache", "dizziness", "allergic reaction"],
        "taste": ["pleasant taste", "tastes good", "bad taste", "tastes awful", "strong odor"],
        "value": ["worth the money", "good value", "overpriced", "too expensive", "waste of money"]
    }
    aspect_sentiments = {"efficacy": None, "side_effects": None, "taste": None, "value": None}
    for aspect, keywords in aspect_keywords.items():
        aspect_score = 0
        keyword_found = False
        for keyword in keywords:
            if keyword in clean_text.lower():
                aspect_score += analyzer.polarity_scores(clean_text)["compound"]
                keyword_found = True
        if keyword_found:
            if aspect_score > 0.3:
                aspect_sentiments[aspect] = "Positive"
            elif aspect_score < -0.3:
                aspect_sentiments[aspect] = "Negative"
            else:
                aspect_sentiments[aspect] = "Mixed"
    return aspect_sentiments

# Sample usage for demonstration
sample_reviews = [
    "This product worked wonders for my anxiety. No side effects at all! Tastes great too, and worth every penny.",
    "Didn't work at all. I feel like I wasted my money. Also, the taste was terrible.",
    "Works well but gave me headaches. Good value for the results though."
]

# Analyze each sample review
results = [analyze_aspect_sentiment_vader(review) for review in sample_reviews]

# Prepare the results in a DataFrame for display
df_results = pd.DataFrame(results)
df_results["Review Text"] = sample_reviews  # Add original text for reference


# Helper functions for cleaning and handling the data (from webMD.py)
def clean_age(age_str):
    if age_str and not re.match(r'\d{1,2}/\d{1,2}/\d{4}', age_str):  # Ignore if it's a date
        return age_str.replace("Age:", "").strip()  # Remove 'Age:' prefix and any surrounding spaces
    return None  # Return None for dates or invalid entries

def clean_supplement_time(supp_time_str):
    if supp_time_str and not re.match(r'\d{1,2}/\d{1,2}/\d{4}', supp_time_str):  # Ignore if it's a date
        return supp_time_str.strip()  # Just trim spaces
    return 'Unknown'  # Return 'Unknown' for missing or invalid entries

def clean_condition(condition_str):
    if condition_str:
        return condition_str.replace("Condition:", "").strip()  # Remove 'Condition:' prefix
    return 'Unknown'  # Return 'Unknown' if no condition is found

def clean_rating(rating_str):
    if rating_str:
        return rating_str.replace("Overall rating", "").strip()  # Remove 'Overall rating' prefix
    return rating_str

def handle_name(name_str):
    if name_str is None or name_str == '' or re.match(r'\d{1,2}/\d{1,2}/\d{4}', name_str):  # If name is missing or it's a date
        return 'anonymous'
    return name_str

# WebMD scraping function remains unchanged
def scrape_webmd(url):
    driver = create_driver()
    all_reviews = []  # List to store all the reviews

    # Loop through multiple pages (adjust the range for more pages as needed)
    page = 1
    while True:
        page_url = f"{url}?page={page}&next_page=true"
        driver.get(page_url)
        time.sleep(5)  # Allow time for the page to load
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Find all review sections
        reviews = soup.find_all('div', class_='review-details-holder')
        
        if not reviews:
            # Break the loop if no more reviews are found
            break
        
        for review in reviews:
            try:
                # Extract user info (name, age, supplement time)
                user_info = review.find('div', class_='card-header')
                if user_info:
                    user_info_text = user_info.get_text(strip=True)
                    # Initialize variables
                    name = None
                    age = None
                    supplement_time = None

                    # Split on '|' to separate name/age from supplement time
                    parts = user_info_text.split('|')
                    if len(parts) > 0:
                        name_age_part = parts[0].strip()
                        age_match = re.search(r'Age:\s*(\d{2}-\d{2}|75 or over)', name_age_part)
                        if age_match:
                            name = name_age_part.split('Age:')[0].strip()  # Name is before "Age:"
                            age = age_match.group(1).strip()  # Extract age
                        else:
                            name = name_age_part

                    if len(parts) > 1:
                        supp_part = parts[1].strip()
                        if supp_part.startswith('On supplement for'):
                            supplement_time = supp_part
                        else:
                            if re.search(r'\d{2}-\d{2}|75 or over', supp_part):
                                age = supp_part  # Assign as age if format matches age
                            else:
                                supplement_time = supp_part

                    # Clean up the age and supplement time format, and filter out dates
                    age = clean_age(age)
                    supplement_time = clean_supplement_time(supplement_time)
                    name = handle_name(name)  # Handle missing or invalid names

                    name_text = name
                    supplement_time_text = supplement_time
                else:
                    name_text = 'anonymous'
                    supplement_time_text = 'Unknown'

                # Extract condition
                condition = review.find('strong', class_='condition')
                condition_text = clean_condition(condition.get_text(strip=True)) if condition else 'Unknown'

                # Extract overall rating
                overall_rating = review.find('div', class_='overall-rating')
                rating_text = clean_rating(overall_rating.get_text(strip=True)) if overall_rating else 'No Rating'

                # Extract review text
                review_text = review.find('div', class_='description')
                review_text_text = review_text.get_text(strip=True) if review_text else 'No Review Text'

                all_reviews.append([name_text, supplement_time_text, condition_text, rating_text, review_text_text])
            except Exception as e:
                print(f"Error extracting data from a review: {e}")

        # Increment the page number to scrape the next page
        page += 1

    driver.quit()

    # Save all the reviews into a DataFrame and export it to a CSV
    df = pd.DataFrame(all_reviews, columns=['Name', 'Supplement Time', 'Condition', 'Rating', 'Review Text'])
    output_file = 'webmd_all_reviews.csv'
    df.to_csv(output_file, index=False)
    return output_file




# Function to summarize reviews using BART
def summarize_reviews_bart(reviews, max_length=150):
    concatenated_reviews = " ".join(reviews)
    inputs = bart_tokenizer.encode(concatenated_reviews, return_tensors="pt", max_length=512, truncation=True)
    summary_ids = bart_model.generate(inputs, max_length=max_length, min_length=40, length_penalty=2.0, num_beams=4, early_stopping=True)
    summary = bart_tokenizer.decode(summary_ids[0], skip_special_tokens=True)
    return summary

# Function to clean the reviews text
def clean_text(text):
    # Replace encoded apostrophes and special characters with plain text equivalents
    text = text.replace("&#39;", "'")  # Replacing encoded apostrophe
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)  # Remove non-ASCII characters
    text = re.sub(r'\s+', ' ', text)  # Remove extra whitespaces
    return text.strip()

# Function to parse the HTML and extract product details
def parse_product_details(html):
    soup = BeautifulSoup(html, 'html.parser')
    products = []

    for product in soup.find_all('div', {'data-component-type': 's-search-result'}):
        # Extract ASIN from the data-asin attribute
        asin = product.get('data-asin', '').strip()

        # Product Name
        product_name_element = product.h2
        product_name = product_name_element.text.strip() if product_name_element else "No Product Name"

        # Price (whole and fractional)
        price_whole = product.find('span', {'class': 'a-price-whole'})
        price_fraction = product.find('span', {'class': 'a-price-fraction'})
        price = f"${price_whole.text.strip()}{price_fraction.text.strip()}" if price_whole and price_fraction else "No Price"

        # Rating
        rating_element = product.find('span', {'class': 'a-icon-alt'})
        rating = rating_element.text.strip() if rating_element else "No Rating"

        # Ratings Count
        ratings_count_element = product.find('span', {'class': 'a-size-base s-underline-text'})
        if ratings_count_element:
            ratings_count_text = ratings_count_element.text.replace(',', '').strip()
            try:
                ratings_number = int(ratings_count_text)
            except ValueError:
                ratings_number = 0
        else:
            ratings_number = 0

        # Product Link
        product_link_element = product.find('a', {'class': 'a-link-normal s-no-outline'}, href=True)
        product_link = 'https://www.amazon.com' + product_link_element['href'] if product_link_element else 'No Link'

        # Append parsed product details including ASIN
        products.append({
            'Product ID': asin,             # ASIN extracted here
            'Product Name': product_name,
            'Product Link': product_link,
            'Price': price,
            'Rating': rating,
            'Ratings Count': ratings_number
        })

    return products if products else None  # Return None if no products found



# Function to parse iHerb product details and extract rating count
def parse_iherb_product_details(html):
    soup = BeautifulSoup(html, 'html.parser')
    products = []

    product_divs = soup.find_all('div', class_='product-cell-container col-xs-12 col-sm-12 col-md-8 col-lg-6')
    for product in product_divs:
        # Product Name
        product_name = product.find('a', class_='absolute-link-wrapper')
        product_name = product_name['title'] if product_name else "No Product Name"

        # Price
        price = product.find('div', class_='product-price-text-nowrap')
        price = price.text.strip() if price else "No Price"

        # Rating
        rating_element = product.find('a', class_='stars scroll-to')
        product_rating = rating_element['title'].split(' - ')[0] if rating_element else "No Rating"

        # Updated Ratings Count Extraction
        ratings_count_element = product.find('a', class_='rating-count scroll-to')
        if ratings_count_element:
            ratings_count_span = ratings_count_element.find('span')
            ratings_count_text = ratings_count_span.get_text(strip=True) if ratings_count_span else '0'
            ratings_count_text = ratings_count_text.replace(',', '')
            try:
                ratings_count = int(ratings_count_text)
            except ValueError:
                ratings_count = 0
        else:
            ratings_count = 0

        # Product Link
        product_link = product.find('a', class_='absolute-link-wrapper', href=True)
        product_link = 'https://www.iherb.com' + product_link['href'] if product_link else 'No Link'

        # Append parsed product details
        products.append({
            'Product Name': product_name,
            'Product Link': product_link,
            'Price': price,
            'Rating': product_rating,
            'Ratings Count': ratings_count
        })

    return products if products else None  # Return None if no products found



# Function to perform sentiment analysis using VADER and then summarize using BART
def analyze_and_summarize_sentiment(reviews):
    if not reviews:
        return "No Reviews", 0, "No Summary"

    total_sentiment = 0
    cleaned_reviews = []
    for review in reviews:
        review_text = review.get('text', '')
        cleaned_text = clean_text(review_text)
        cleaned_reviews.append(cleaned_text)
        sentiment_score = analyzer.polarity_scores(cleaned_text)['compound']
        total_sentiment += sentiment_score

    avg_sentiment = total_sentiment / len(cleaned_reviews)

    # Determine sentiment based on the average compound score
    if avg_sentiment >= 0.7:
        sentiment_label = "Highly Positive"
    elif 0.3 <= avg_sentiment < 0.7:
        sentiment_label = "Positive"
    elif -0.3 <= avg_sentiment < 0.3:
        sentiment_label = "Mixed"
    elif -0.7 <= avg_sentiment < -0.3:
        sentiment_label = "Negative"
    else:
        sentiment_label = "Highly Negative"

    # Generate a summary of the reviews using BART
    summary = summarize_reviews_bart(cleaned_reviews)

    return sentiment_label, avg_sentiment, summary

# Asynchronous function to fetch reviews for a single product using Playwright
async def fetch_amazon_reviews(playwright, product_name, product_link):
    if product_link == 'No Link':
        print(f"Skipping product without a valid link: {product_name}")
        return []

    # Retry mechanism to load page multiple times in case of failure
    for attempt in range(3):
        try:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=get_random_user_agent())
            print(f"Fetching reviews for: {product_name}")
            await page.goto(product_link, timeout=60000)  # Increased timeout to 60 seconds
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')

            # Locate and parse the reviews section from the product page
            reviews = []
            for review in soup.find_all('div', {'data-hook': 'review'}, limit=30):  # Limit to 30 reviews
                # Extract review text
                review_text_element = review.find('span', {'data-hook': 'review-body'})
                review_text = review_text_element.get_text(strip=True) if review_text_element else "No Review Text"

                # Extract review date
                review_date_element = review.find('span', {'data-hook': 'review-date'})
                if review_date_element:
                    review_date_text = review_date_element.get_text(strip=True)
                    match = re.search(r'on\s+(.*)', review_date_text)
                    if match:
                        date_str = match.group(1)
                        try:
                            review_date = datetime.datetime.strptime(date_str, '%B %d, %Y')
                        except ValueError:
                            review_date = None
                    else:
                        review_date = None
                else:
                    review_date = None

                reviews.append({'text': review_text, 'date': review_date})

            await browser.close()
            return reviews if reviews else [{'text': 'No Reviews', 'date': None}]

        except PlaywrightTimeoutError:
            print(f"Attempt {attempt + 1} failed for product: {product_name}. Retrying...")
            if attempt == 2:
                print(f"Failed to fetch reviews for: {product_name} after 3 attempts.")
                await browser.close()
                return [{'text': 'No Reviews', 'date': None}]

    return []


# Function to scrape product reviews and perform sentiment analysis and summarization
async def scrape_amazon_reviews(url, total_pages=1):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        page = await browser.new_page(user_agent=get_random_user_agent())

        all_products = []
        current_page = 1
        try:
            await page.goto(url)
            while current_page <= total_pages:
                print(f"Scraping page: {current_page}")

                # Wait for the product listings to load
                try:
                    await page.wait_for_selector('div.s-main-slot', timeout=15000)
                except PlaywrightTimeoutError:
                    print("Timeout while waiting for product listings to load.")
                    break

                html = await page.content()
                product_details = parse_product_details(html)

                if product_details:
                    all_products.extend(product_details)
                else:
                    print(f"No products found on page {current_page}")
                    break  # Exit the loop if no products are found

                current_page += 1

        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            await browser.close()

        # Now process the products and get reviews, sentiment, and summary
        all_reviews = []
        for product in all_products:
            reviews = await fetch_amazon_reviews(playwright, product['Product Name'], product['Product Link'])

            # Extract dates from reviews
            review_dates = [review['date'] for review in reviews if review['date'] is not None]

            # Find the latest date
            if review_dates:
                latest_review_date = max(review_dates)
                # Format the date as MM/DD/YYYY
                latest_review_date_str = latest_review_date.strftime('%m/%d/%Y')
            else:
                latest_review_date_str = 'No Reviews'

            # Perform sentiment analysis and summarization
            sentiment, score, summary = analyze_and_summarize_sentiment(reviews)

            product['Summary Sentiment'] = sentiment
            product['Sentiment Score'] = score
            product['Review Summary'] = summary
            product['Latest Review Date'] = latest_review_date_str  # Add the latest review date

            all_reviews.append(product)

        return all_reviews



# Function to run asyncio in a synchronous environment and scrape Amazon reviews
def scrape_amazon_products_reviews(base_url, total_pages=1):
    loop = asyncio.get_event_loop()
    reviews = loop.run_until_complete(scrape_amazon_reviews(base_url, total_pages))
    return reviews

# Function to scrape with Playwright and BeautifulSoup
async def scrape_iherb_product_details(url, xpath_query, num_pages):
    product_list = []
    # Start Playwright
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)

        for page_number in range(num_pages):
            page_url = f"{url}&p={page_number + 1}"
            page = await browser.new_page(user_agent=get_random_user_agent())

            # Navigate to the URL
            await page.goto(page_url)

            # Wait for content to load
            await page.wait_for_selector('body')

            # Extract content via XPath
            element = page.locator(xpath_query)

            if await element.count() > 0:
                # Extract the HTML content of the first matching element
                element_html = await element.first.inner_html()

                # Parse the HTML with BeautifulSoup
                soup = BeautifulSoup(element_html, 'html.parser')
                product_divs = soup.find_all('div', class_='product-cell-container col-xs-12 col-sm-12 col-md-8 col-lg-6')

                for product in product_divs:
                    id_element = product.find('div', class_='product ga-product')
                    product_id = id_element['id'].replace('pid_', '') if id_element else None

                    product_link = product.find('a', class_='absolute-link product-link')
                    product_name = product_link['title'] if product_link else None
                    product_href = product_link['href'] if product_link else None

                    rating_element = product.find('a', class_='stars scroll-to')
                    product_rating = rating_element['title'].split(' - ')[0] if rating_element else None

                    product_price = product.find('span', class_='price')
                    product_price = product_price.find('bdi').get_text(strip=True) if product_price and product_price.find('bdi') else None

                    # Updated Ratings Count Extraction
                    ratings_count_element = product.find('a', class_='rating-count scroll-to')
                    if ratings_count_element:
                        ratings_count_span = ratings_count_element.find('span')
                        ratings_count_text = ratings_count_span.get_text(strip=True) if ratings_count_span else '0'
                        ratings_count_text = ratings_count_text.replace(',', '')
                        try:
                            ratings_count = int(ratings_count_text)
                        except ValueError:
                            ratings_count = 0
                    else:
                        ratings_count = 0

                    product_list.append({
                        'Product Name': product_name,
                        'Product Price': product_price,
                        'Product Rating': product_rating,
                        'Ratings Count': ratings_count,
                        "Product ID": product_id,
                        "Product Link": product_href,
                    })
            await page.close()

        # Close the browser
        await browser.close()
    return product_list


async def fetch_iherb_reviews(playwright, product_name, product_id, product_href, num_review_pages=1):
    if product_href is None or product_id is None:
        print(f"Skipping product without a valid link: {product_name}")
        return [{'text': 'No Reviews'}]  # Changed here

    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
    page = await context.new_page()
    await page.set_extra_http_headers({
        'User-Agent': f'{get_random_user_agent()}'
    })

    reviews = []
    for page_number in range(num_review_pages):
        print(f"Fetching reviews for: {product_name} ({page_number + 1}/{num_review_pages} pages)...")
        url = product_href.replace('iherb.com/pr', 'iherb.com/r') + f'?sort=6&isshowtranslated=true&p={page_number + 1}'
        await page.goto(url)
        try:
            await page.wait_for_selector('#reviews', timeout=5000)
        except Exception:
            print(f"No reviews found for {product_name} on page {page_number + 1}.")
            return [{'text': 'No Reviews Found'}]  # Changed here

        # Locate the review container
        review_blocks = page.locator('div#reviews div.MuiBox-root.css-1v71s4n')

        # Get the number of reviews on the page
        review_count = await review_blocks.count()
        if review_count == 0:
            return [{'text': 'No Reviews'}]  # Changed here

        # Loop through each review block
        for i in range(review_count):
            review = review_blocks.nth(i)

            # Check if the "Read more" button exists in this specific review block
            read_more_button = review.locator('span.MuiTypography-root.MuiTypography-body2.css-ptz5k')
            if await read_more_button.count() > 0:
                # Check if the CAPTCHA is present
                captcha_present = await page.locator('#px-captcha-wrapper').count()
                if captcha_present > 0:
                    print(f"CAPTCHA detected on {product_name}.")
                    captcha_div = 'div#px-captcha-wrapper'
                    await page.evaluate(f'document.querySelector("{captcha_div}").remove();')

                # Attempt to click the "Read more" button with force
                try:
                    await read_more_button.click(force=True)
                except Exception as e:
                    print(f"Failed to click 'Read more' for {product_name}: {str(e)}")
                    continue  # Skip this review if the click fails

                # Optionally, wait for the full review text to load
                await page.wait_for_timeout(1000)  # Adjust timeout based on loading speed

            # Now extract the full review text (whether expanded or not)
            review_text_element = review.locator('span.__react-ellipsis-js-content, div.review-full-text')
            review_text = await review_text_element.text_content() if await review_text_element.count() > 0 else "No Review Text"

            # Append as a dictionary
            reviews.append({'text': review_text.strip()})

    await browser.close()
    return reviews if reviews else [{'text': 'No Reviews'}]



async def scrape_iherb_product_reviews(product_list, num_review_pages):
    async with async_playwright() as playwright:
        for product in product_list:
            product_name = product['Product Name']
            product_id = product['Product ID']
            product_href = product['Product Link']

            reviews = await fetch_iherb_reviews(playwright, product_name, product_id, product_href, num_review_pages=num_review_pages)
            sentiment, score, summary = analyze_and_summarize_sentiment(reviews)
            product.update({
                "Summary Sentiment": sentiment,
                "Sentiment Score": score,
                "Review Summary": summary
            })

    return product_list


async def scrape_iherb_product_reviews_main(url, xpath_query, num_pages, num_review_pages):
    # Stage 1: Scrape product details
    product_list = await scrape_iherb_product_details(url, xpath_query, num_pages)

    # Stage 2: Scrape product reviews
    product_list_with_reviews = await scrape_iherb_product_reviews(product_list, num_review_pages)

    df = pd.DataFrame(product_list_with_reviews)
    return df

@app.route('/')
def index():
    return render_template('index.html')


# Handling the scraping request and how many pages to scrape
@app.route('/scrape', methods=['POST'])
def scrape():
    url = request.form['url']
    pages = int(request.form.get('reviewCount', 1))  # Default is 1 page, or you can specify how many in the form

    if 'amazon.com' in url:
        reviews = scrape_amazon_products_reviews(url, total_pages=pages)

        # Save the results to a CSV file
        df = pd.DataFrame(reviews)

               # Include 'Product ID' in the DataFrame columns
        df = df[['Product ID', 'Product Name', 'Product Link', 'Price', 'Rating', 'Ratings Count',
                 'Latest Review Date','Summary Sentiment', 'Sentiment Score', 'Review Summary']]

        output_file = 'amazon_products_with_sentiment_and_summary.csv'
        df.to_csv(output_file, index=False)
        return send_file(output_file, as_attachment=True, mimetype='text/csv')
    elif 'iherb.com' in url:
        # XPath for iHerb product listings
        xpath_query = '//*[@id="FilteredProducts"]/div[1]/div[2]/div[2]'
        num_review_pages = 2  # Number of review pages to scrape per product
        num_pages = pages  # Number of pages to scrape

        df = asyncio.run(scrape_iherb_product_reviews_main(url, xpath_query, num_pages=num_pages, num_review_pages=num_review_pages))
        df.to_csv('iherb_products_with_sentiment.csv', index=False)
        return send_file('iherb_products_with_sentiment.csv', as_attachment=True, mimetype='text/csv')
    elif 'webmd.com' in url:
        csv_file = scrape_webmd(url)
        return send_file(csv_file, as_attachment=True, mimetype='text/csv')

    else:
        return "Invalid URL, please provide a valid Amazon, iHerb, or WebMD URL."


# Flag to ensure the browser only opens once
has_opened_browser = False

if __name__ == '__main__':
    def open_browser():
        global has_opened_browser
        if not has_opened_browser:
            time.sleep(3)  # Delay to ensure the server is fully up
            webbrowser.open("http://127.0.0.1:5000")
            print("Use the URL from the results page.")
            has_opened_browser = True

    # Only start the browser in the reloaded process
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Timer(1, open_browser).start()

    app.run(debug=True)
