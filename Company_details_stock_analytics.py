import selenium
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import os
import time
import requests
import pandas as pd
import logging
from tqdm import tqdm

# Set up logging
logging.basicConfig(
    filename='scraping.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def setup_driver():
    """Initialize and return Chrome webdriver with basic options"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # Run in headless mode
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    return webdriver.Chrome(options=options)

def save_logo(logo_url, company_name, logo_dir):
    """Save company logo to specified directory"""
    try:
        logo_filename = os.path.join(logo_dir, f"{company_name.replace(' ', '_')}_logo.svg")
        response = requests.get(logo_url, timeout=10)
        response.raise_for_status()
        
        with open(logo_filename, "wb") as logo_file:
            logo_file.write(response.content)
        logging.info(f"Logo saved successfully for {company_name}")
        return logo_filename
    except Exception as e:
        logging.error(f"Failed to save logo for {company_name}: {str(e)}")
        return None

def scrape_company_data(url, driver, logo_dir):
    """Scrape company data from given URL"""
    try:
        driver.get(url + "company/")
        time.sleep(5)  # Allow page to load
        
        # Extract description
        description_element = driver.find_element(By.XPATH, '//*[@id="main"]/div[2]/div[1]')
        description_text = description_element.text
        
        # Extract company details
        company_details_element = driver.find_element(By.XPATH, '//*[@id="main"]/div[2]/div[2]')
        company_name = company_details_element.find_element(By.CLASS_NAME, "text-2xl").text
        
        # Extract and save logo
        logo_element = company_details_element.find_element(By.TAG_NAME, "img")
        logo_url = logo_element.get_attribute("src")
        logo_path = save_logo(logo_url, company_name, logo_dir)
        
        # Extract company details
        company_details = {
            "Company Name": company_name,
            "Company Description": description_text.split("\n", 1)[-1],
            "Logo Path": logo_path
        }
        
        # Extract table data
        rows = company_details_element.find_elements(By.TAG_NAME, "tr")
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) == 1 and "Address:" in row.text.strip():
                company_details["Address"] = row.text.replace("Address:", "").strip()
            elif len(cells) == 2:
                key = cells[0].text.strip()
                value = cells[1].text.strip()
                company_details[key] = value
                
        return company_details
    
    except Exception as e:
        logging.error(f"Error scraping {url}: {str(e)}")
        return None

def main():
    # Read input data
    df1 = pd.read_csv("Data/stock_analysis_screener_usa.csv")
    df2 = pd.read_csv("Data/stock_analysis_screener_OTC_USA.csv")
    
    # Combine dataframes
    all_companies = pd.concat([df1, df2], ignore_index=True)
    
    # Create directory for logos
    logo_dir = r"Data/company_logos_stock_analysis"
    os.makedirs(logo_dir, exist_ok=True)
    
    # Initialize results list and driver
    results = []
    driver = setup_driver()
    
    try:
        # Process each company with progress bar
        for _, row in tqdm(all_companies.iterrows(), total=len(all_companies), desc="Scraping companies"):
            try:
                company_data = scrape_company_data(row['Link'], driver, logo_dir)
                if company_data:
                    company_data['Original Link'] = row['Link']
                    results.append(company_data)
                    
                    # Save intermediate results every 10 companies
                    if len(results) % 10 == 0:
                        pd.DataFrame(results).to_csv('intermediate_results.csv', index=False)
                        
            except Exception as e:
                logging.error(f"Error processing company {row['Link']}: {str(e)}")
                continue
                
    finally:
        driver.quit()
    
    # Save final results
    results_df = pd.DataFrame(results)
    results_df.to_csv('company_details.csv', index=False)
    logging.info(f"Scraping completed. Processed {len(results)} companies successfully.")

if __name__ == "__main__":
    main()