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
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
import threading

# Set up logging with thread safety
logging.basicConfig(
    filename='Data/scraping.log',
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger()
log_lock = threading.Lock()

current_results = []

# Thread-safe queue for results
results_queue = queue.Queue()

def setup_driver():
    """Initialize and return Chrome webdriver with basic options"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    return webdriver.Chrome(options=options)

def safe_log(message, level='info'):
    """Thread-safe logging function"""
    with log_lock:
        if level == 'error':
            logger.error(message)
        else:
            logger.info(message)

def save_logo(logo_url, company_name, logo_dir):
    """Save company logo to specified directory"""
    try:
        logo_filename = os.path.join(logo_dir, f"{company_name.replace(' ', '_')}_logo.svg")
        response = requests.get(logo_url, timeout=10)
        response.raise_for_status()
        
        with open(logo_filename, "wb") as logo_file:
            logo_file.write(response.content)
        safe_log(f"Logo saved successfully for {company_name}")
        return logo_filename
    except Exception as e:
        safe_log(f"Failed to save logo for {company_name}: {str(e)}", 'error')
        return None

def scrape_company_data(company_info):
    """Scrape company data with its own webdriver instance"""
    url = company_info['Link']
    logo_dir = company_info['logo_dir']
    driver = None
    
    try:
        driver = setup_driver()
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
            "Logo Path": logo_path,
            "Original Link": url
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
        
        results_queue.put(company_details)
        return True
        
    except Exception as e:
        safe_log(f"Error scraping {url}: {str(e)}", 'error')
        return False
        
    finally:
        if driver:
            driver.quit()

def save_intermediate_results(output_file= "Data/SA_intermediate_results.csv"):
    """Save current results from queue to CSV"""
    
    while not results_queue.empty():
        current_results.append(results_queue.get())
    
    if current_results:
        pd.DataFrame(current_results).to_csv(output_file, index=False)
        safe_log(f"Saved intermediate results with {len(current_results)} entries")
    

def main():
    # Read input data
    df1 = pd.read_csv("Data/stock_analysis_screener_usa.csv")
    df2 = pd.read_csv("Data/stock_analysis_screener_OTC_USA.csv")
    
    # Combine dataframes
    all_companies = pd.concat([df1, df2], ignore_index=True)
    # all_companies = all_companies.head(100)  # Limit to first 100 companies for testing
    # Create directory for logos
    logo_dir = r"Data/company_logos_stock_analysis"
    os.makedirs(logo_dir, exist_ok=True)
    
    # Prepare company info with logo directory
    companies_to_process = [
        {'Link': row['Link'], 'logo_dir': logo_dir}
        for _, row in all_companies.iterrows()
    ]
    
    # Initialize progress bar
    pbar = tqdm(total=len(companies_to_process), desc="Scraping companies")
    
    # Process companies with thread pool
    max_workers = min(10, len(companies_to_process))  # Limit max threads
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_url = {
            executor.submit(scrape_company_data, company): company['Link']
            for company in companies_to_process
        }
        
        # Process completed tasks
        completed_count = 0
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                success = future.result()
                if success:
                    completed_count += 1
                    
                    # Save intermediate results every 10 companies
                    if completed_count % 10 == 0:
                        save_intermediate_results()
                        
            except Exception as e:
                safe_log(f"Exception processing {url}: {str(e)}", 'error')
            
            pbar.update(1)
    
    pbar.close()
    
    # Save final results
    save_intermediate_results("Data/SA_Comapany_details_final_results.csv")
    safe_log(f"Scraping completed. Processed {completed_count} companies successfully.")

if __name__ == "__main__":
    main()