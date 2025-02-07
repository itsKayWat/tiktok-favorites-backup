import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from datetime import datetime
import subprocess
import re
from urllib.parse import urlparse, unquote

def display_welcome_message():
    print("""
╔════════════════════════════════════════════════════════════════╗
║                 TikTok Collection Backup Tool                  ║
╚════════════════════════════════════════════════════════════════╝

This tool will create a backup of a TikTok collection including:
- All videos in the collection
- Video metadata and information
- Collection name and details

Note: Private videos will be skipped but their URLs will be saved
""")

def get_collection_url():
    print("\nEnter TikTok Favorites share collection URL: ", end="")
    return input().strip()

def extract_collection_name(driver, url):
    try:
        # Wait for the collection title to load
        collection_title = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1[data-e2e='collection-title']"))
        ).text
        
        # Clean the collection name for file system
        clean_name = re.sub(r'[<>:"/\\|?*]', '', collection_title)
        return clean_name
    except:
        # Fallback: Extract from URL
        try:
            decoded_url = unquote(url)
            collection_name = decoded_url.split('collection/')[1].split('/')[0]
            return collection_name.replace('%20', ' ')
        except:
            return f"Collection_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

def create_backup_directory(collection_name):
    date_str = datetime.now().strftime("%B %d")
    day = int(datetime.now().strftime("%d"))
    suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') if day % 10 < 4 else 'th'
    date_str = f"{date_str}{suffix}-{datetime.now().strftime('%Y')}"
    
    base_dir = f"{collection_name}_{date_str}"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backup_dir = os.path.join(script_dir, base_dir)
    os.makedirs(backup_dir, exist_ok=True)
    
    return backup_dir

def scrape_collection_videos(driver, backup_dir):
    print("\nScraping videos from collection...")
    original_url = driver.current_url
    
    def ensure_collection_page():
        current_url = driver.current_url
        if "/foryou" in current_url or "?is_from_webapp" in current_url:
            print("Detected For You page, returning to collection...")
            driver.get(original_url)
            time.sleep(3)  # Wait longer for page to properly load
            return True
        return False
    
    # Initial scroll to load all videos
    print("Loading all videos...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_attempts = 0
    max_scroll_attempts = 30  # Prevent infinite scrolling
    
    while scroll_attempts < max_scroll_attempts:
        # Check and correct page before each scroll
        ensure_collection_page()
        
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
        scroll_attempts += 1

    # Ensure we're on collection page before finding videos
    ensure_collection_page()

    # Find all video containers
    video_containers = driver.find_elements(By.CSS_SELECTOR, "div[data-e2e='collection-item']")
    total_videos = len(video_containers)
    print(f"Found {total_videos} videos")

    # Process each video
    for index, container in enumerate(video_containers, 1):
        try:
            print(f"\nProcessing video {index}/{total_videos}")
            
            # Check page before processing each video
            if ensure_collection_page():
                # Refresh container references if we had to redirect
                video_containers = driver.find_elements(By.CSS_SELECTOR, "div[data-e2e='collection-item']")
                container = video_containers[index-1]
            
            # Find and verify video link
            video_link = container.find_element(By.CSS_SELECTOR, "a[href*='/video/']")
            video_url = video_link.get_attribute('href')
            
            if not video_url or "foryou" in video_url:
                print("Invalid video URL, skipping...")
                continue

            # Clean the video URL to remove any webapp parameters
            video_url = video_url.split('?')[0]
            
            # Store original window handle
            original_window = driver.current_window_handle
            
            # Open video in new tab
            driver.execute_script("window.open(arguments[0], '_blank');", video_url)
            time.sleep(2)
            
            # Switch to new tab
            new_window = [handle for handle in driver.window_handles if handle != original_window][0]
            driver.switch_to.window(new_window)
            
            # Verify we're on the correct video page
            if "/video/" not in driver.current_url or "foryou" in driver.current_url:
                print("Incorrect video page loaded, skipping...")
                driver.close()
                driver.switch_to.window(original_window)
                continue
            
            # Process video
            process_video(driver, backup_dir)
            
            # Clean up
            driver.close()
            driver.switch_to.window(original_window)
            ensure_collection_page()  # Verify we're back on collection page
            
        except Exception as e:
            print(f"Error processing video: {str(e)}")
            # Clean up on error
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
            ensure_collection_page()
            continue

    return True

def setup_chrome_profile():
    chrome_options = webdriver.ChromeOptions()
    
    # Get the correct path for Windows
    user_data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'Google', 'Chrome', 'User Data')
    
    # Add necessary options to prevent crashes and detection
    chrome_options.add_argument(f'--user-data-dir={user_data_dir}')
    chrome_options.add_argument('--profile-directory=Default')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--remote-debugging-port=9222')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Close any existing Chrome instances
    os.system("taskkill /f /im chrome.exe")
    time.sleep(2)
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        # Mask selenium's presence
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        print(f"Error initializing Chrome with profile: {str(e)}")
        print("\nTrying alternative method without user profile...")
        
        try:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            print(f"Error with alternative method: {str(e)}")
            sys.exit("Could not initialize Chrome. Please make sure Chrome is installed.")

def main():
    display_welcome_message()
    
    # Get collection URL
    collection_url = get_collection_url()
    
    # Initialize browser with profile
    print("\nInitializing browser...")
    driver = setup_chrome_profile()
    
    try:
        # Load collection page with handling for automation detection
        print("\nLoading collection page...")
        driver.get(collection_url)
        time.sleep(3)  # Initial wait
        
        # Refresh to bypass automation detection
        driver.refresh()
        time.sleep(3)
        
        # Get collection name and create backup directory
        collection_name = extract_collection_name(driver, collection_url)
        backup_dir = create_backup_directory(collection_name)
        
        # Scrape videos
        scrape_collection_videos(driver, backup_dir)
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main() 