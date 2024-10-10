import asyncio
from flask import Flask, render_template, request, send_file
from bs4 import BeautifulSoup
import pandas as pd
import nest_asyncio
import random
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import re
import time
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from flask import Flask, render_template, request, send_file
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor

# Apply nested asyncio loop patch
nest_asyncio.apply()

# Initialize Flask app
app = Flask(__name__)

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
def create_driver():
    # Correct indentation
    chrome_options = Options()  # No extra space here
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")

    chrome_service = Service(executable_path="C:/mysql/Chromedriver.exe")
    driver = webdriver.Chrome(service=chrome_service, options=chrome_options)

    return driver  # Make sure the return statement is inside the function


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


# Initialize VADER sentiment analyzer
analyzer = SentimentIntensityAnalyzer()

# Function to get random user agent
def get_random_user_agent():
    return random.choice(USER_AGENTS)

# Function to clean the reviews text
def clean_text(text):
    # Replace encoded apostrophes and special characters with plain text equivalents
    text = text.replace("&#39;", "'")  # Replacing encoded apostrophe
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)  # Remove non-ASCII characters
    text = re.sub(r'\s+', ' ', text)  # Remove extra whitespaces
    return text.strip()

# Updated function to perform sentiment analysis using VADER
def analyze_sentiment(reviews):
    if not reviews:
        return "No Reviews", 0

    total_sentiment = 0
    cleaned_reviews = [clean_text(review) for review in reviews]  # Clean reviews before analyzing

    print(f"Cleaned Reviews for analysis: {cleaned_reviews}")  # Print cleaned reviews for debugging

    for review in cleaned_reviews:
        sentiment_score = analyzer.polarity_scores(review)['compound']  # Use VADER compound score for each review
        total_sentiment += sentiment_score

    avg_sentiment = total_sentiment / len(cleaned_reviews)  # Average sentiment score across all reviews
    print(f"Average Sentiment Score: {avg_sentiment}")  # Debugging output to see the score

    # Determine sentiment based on the average compound score
    if avg_sentiment >= 0.7:
        return "Highly Positive", avg_sentiment
    elif 0.3 <= avg_sentiment < 0.7:
        return "Positive", avg_sentiment
    elif -0.3 <= avg_sentiment < 0.3:
        return "Mixed", avg_sentiment
    elif -0.7 <= avg_sentiment < -0.3:
        return "Negative", avg_sentiment
    else:
        return "Highly Negative", avg_sentiment

# Asynchronous function to fetch reviews for a single product using Playwright
async def fetch_amazon_reviews(playwright, product_name, product_link):
    if product_link == 'No Link':
        print(f"Skipping product without a valid link: {product_name}")
        return []

    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page(user_agent=get_random_user_agent())
    print(f"Fetching reviews for: {product_name}")

    await page.goto(product_link)
    content = await page.content()
    soup = BeautifulSoup(content, 'html.parser')

    # Locate and parse the reviews section from the product page
    reviews = []
    for review in soup.find_all('div', {'data-hook': 'review'}, limit=30):  # Limit to 30 reviews
        review_text = review.find('span', {'data-hook': 'review-body'}).get_text(strip=True)
        reviews.append(review_text)

    await browser.close()
    return reviews if reviews else ['No Reviews']

# Function to parse the HTML and extract product details
def parse_product_details(html):
    soup = BeautifulSoup(html, 'html.parser')
    products = []

    for product in soup.find_all('div', {'data-component-type': 's-search-result'}):
        # Product Name
        product_name = product.h2.text.strip() if product.h2 else "No Product Name"

        # Price (whole and fractional)
        price_whole = product.find('span', {'class': 'a-price-whole'})
        price_fraction = product.find('span', {'class': 'a-price-fraction'})
        price = f"${price_whole.text.strip()}{price_fraction.text.strip()}" if price_whole and price_fraction else "No Price"

        # Rating
        rating = product.find('span', {'class': 'a-icon-alt'})
        rating = rating.text.strip() if rating else "No Rating"

        # Product Link
        product_link = product.find('a', {'class': 'a-link-normal s-no-outline'}, href=True)
        product_link = 'https://www.amazon.com' + product_link['href'] if product_link else 'No Link'

        # Append parsed product details
        products.append({
            'Product Name': product_name,
            'Product Link': product_link,
            'Price': price,
            'Rating': rating,
        })

    return products if products else None  # Return None if no products found

# Asynchronous function to scrape product links and their reviews using Playwright
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

                # Check for CAPTCHA
                if "Enter the characters you see below" in await page.content():
                    print("Encountered CAPTCHA. Exiting.")
                    break

                html = await page.content()
                product_details = parse_product_details(html)

                if product_details:
                    all_products.extend(product_details)
                else:
                    print(f"No products found on page {current_page}")
                    break  # Exit the loop if no products are found

                if current_page < total_pages:
                    # Try to find the 'Next' button using various selectors
                    next_page_button = await page.query_selector("//a[contains(@aria-label, 'Next')]")
                    if not next_page_button:
                        next_page_button = await page.query_selector("li.a-last a")
                    if not next_page_button:
                        next_page_button = await page.query_selector("a.s-pagination-next")

                    if next_page_button:
                        next_page_url = await next_page_button.get_attribute('href')
                        if next_page_url:
                            next_page_url = 'https://www.amazon.com' + next_page_url
                            print(f"Navigating to next page: {next_page_url}")
                            await asyncio.sleep(random.uniform(2, 5))  # Random delay
                            await page.goto(next_page_url)
                            current_page += 1
                        else:
                            print("No 'href' found for 'Next' button, ending pagination.")
                            break
                    else:
                        print("No 'Next' button found, ending pagination.")
                        break  # No more pages, exit the loop
                else:
                    print("Desired number of pages scraped.")
                    break

        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            await browser.close()

        # Now process the products and get reviews, as before
        all_reviews = []
        for product in all_products:
            reviews = await fetch_amazon_reviews(playwright, product['Product Name'], product['Product Link'])

            # Perform sentiment analysis
            sentiment, score = analyze_sentiment(reviews)
            product['Summary Sentiment'] = sentiment
            product['Sentiment Score'] = score
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
        browser = await playwright.chromium.launch(headless=False)  # You can set headless=False to see the browser in action

        for page_number in range(num_pages):
            page_url = f"{url}&p={page_number + 1}"
            page = await browser.new_page(user_agent=get_random_user_agent())

            # Navigate to the URL
            await page.goto(page_url)

            # Wait for content to load (if necessary, you can use more sophisticated waiting strategies)
            await page.wait_for_selector('body')

            # Extract content via XPath
            element = page.locator(xpath_query)
            print("Element:", await element.count())

            if await element.count() > 0:
                # Extract the HTML content of the first matching element
                element_html = await element.first.inner_html()

                # Parse the HTML with BeautifulSoup
                soup = BeautifulSoup(element_html, 'html.parser')
                product_divs = soup.find_all('div', class_='product-cell-container col-xs-12 col-sm-12 col-md-8 col-lg-6')
                print("product:", product_divs.__len__())
                for product in product_divs:
                    id_element = product.find('div', class_='product ga-product')
                    product_id = id_element['id'] if id_element else None
                    product_id = product_id.replace('pid_', '') if product_id != None else None # Remove 'pid_' from ID

                    product_link = product.find('a', class_='absolute-link product-link')
                    product_name = product_link['title'] if product_link else None
                    product_href = product_link['href'] if product_link else None

                    rating_element = product.find('a', class_='stars scroll-to')
                    product_rating = rating_element['title'] if rating_element else None
                    product_rating = product_rating.split(' - ')[0] if product_rating is not None else None

                    product_price = product.find('span', class_='price')
                    product_price = product_price.find('bdi').get_text(strip=True) if product_price and product_price.find('bdi') else None

                    product_list.append({
                        'Product Name': product_name,
                        'Product Price': product_price,
                        'Product Rating': product_rating,
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
        return []

    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(viewport={'width': 3840, 'height': 2160})
    page = await context.new_page()
    await page.set_extra_http_headers({
    'User-Agent': f'{get_random_user_agent()}'
})

    reviews = []
    for page_number in range(num_review_pages):
        print(f"Fetching reviews for: {product_name}({page_number + 1}/{num_review_pages} pages)...)")
        url = product_href.replace('iherb.com/pr', 'iherb.com/r')+f'?sort=6&isshowtranslated=true&p={page_number+1}'
        await page.goto(url)
        try:
            await page.wait_for_selector('#reviews', timeout=2000)
        except Exception:
            print(f"No reviews found for {product_name} on page {page_number + 1}.")
            return ["No Reviews Found"]
        # Locate the review container
        review_blocks = page.locator('div#reviews div.MuiBox-root.css-1v71s4n')

        # Get the number of reviews on the page
        review_count = await review_blocks.count()
        if review_count == 0:
            return ["No Reviews"]

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

            reviews.append(review_text.strip())

    await browser.close()
    return reviews if reviews else ['No Reviews']


async def scrape_iherb_product_reviews(product_list, num_review_pages):
    async with async_playwright() as playwright:
        for product in product_list:
            product_name = product['Product Name']
            product_id = product['Product ID']
            product_href = product['Product Link']

            reviews = await fetch_iherb_reviews(playwright, product_name, product_id, product_href, num_review_pages=num_review_pages)
            sentiment, score = analyze_sentiment(reviews)
            product.update({
                "Summary Sentiment": sentiment,
                "Sentiment Score": score,
            })

    return product_list


async def scrape_iherb_product_reviews_main(url, xpath_query, num_pages, num_review_pages):
    # Stage 1: Scrape product details
    product_list = await scrape_iherb_product_details(url, xpath_query, num_pages)

    # Stage 2: Scrape product reviews
    product_list_with_reviews = await scrape_iherb_product_reviews(product_list, num_review_pages)

    df = pd.DataFrame(product_list_with_reviews)
    return df

# HTML Form to input the number of pages to scrape
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

        # Reorder columns to move Product Link after Product Name
        df = df[['Product Name', 'Product Link', 'Price', 'Rating', 'Summary Sentiment', 'Sentiment Score']]

        output_file = 'amazon_products_with_sentiment.csv'
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
        return "Invalid URL, please provide a valid Amazon or iHerb URL."

if __name__ == '__main__':
    app.run(debug=True)
