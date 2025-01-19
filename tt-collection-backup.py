import asyncio
import os
import json
from datetime import datetime
from pyppeteer import launch
import sys

def display_welcome_message():
    print("\n╔════════════════════════════════════════════════════════════════╗")
    print("║                 TikTok Collection Backup Tool                  ║")
    print("╚════════════════════════════════════════════════════════════════╝\n")
    print("This tool will create a backup of a TikTok collection including:")
    print("- All videos in the collection")
    print("- Video metadata and information")
    print("- Collection name and details\n")
    print("Note: Private videos will be skipped but their URLs will be saved\n")

async def setup_browser():
    print("Setting up browser with user profile...")
    try:
        # Chrome user data and profile paths
        user_data_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
        profile_directory = "Default"  # or "Profile 1" depending on your setup
        
        chrome_paths = {
            'win32': [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ],
            'linux': ['/usr/bin/google-chrome'],
            'darwin': ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
        }

        executable_path = None
        for path in chrome_paths.get(sys.platform, []):
            if os.path.exists(path):
                executable_path = path
                break

        if not executable_path:
            print("Chrome executable not found!")
            sys.exit(1)

        print(f"Using Chrome at: {executable_path}")
        print(f"Using profile at: {user_data_dir}")

        browser = await launch(
            headless=False,
            executablePath=executable_path,
            userDataDir=user_data_dir,
            args=[
                '--no-sandbox',
                '--window-size=1920,1080',
                f'--profile-directory={profile_directory}',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials'
            ],
            defaultViewport=None,
            ignoreDefaultArgs=['--enable-automation']
        )

        page = await browser.newPage()
        
        # Set user agent to avoid detection
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Add additional headers
        await page.setExtraHTTPHeaders({
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

        return browser, page

    except Exception as e:
        print(f"Browser setup error: {str(e)}")
        sys.exit(1)

def sanitize_filename(filename):
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    filename = ''.join(char for char in filename if ord(char) < 65536 and char.isprintable())
    return filename.strip(' _')

async def handle_collection_videos(page, first_video_url):
    try:
        print("\nNavigating to first video...")
        await page.goto(first_video_url, {
            'waitUntil': 'networkidle0',
            'timeout': 30000
        })
        await asyncio.sleep(3)  # Give more time for the page to fully load

        videos = []
        while True:
            # Wait for video elements to be present
            await page.waitForSelector('video', {'timeout': 10000})
            
            # Get current video information
            video_info = await page.evaluate('''() => {
                const videoElement = document.querySelector('video');
                const descElement = document.querySelector('div[data-e2e="video-desc"]');
                const usernameElement = document.querySelector('h3[data-e2e="video-author-uniqueid"]');
                const collectionTitle = document.querySelector('div[data-e2e="browse-video-desc"] strong');
                const likeCount = document.querySelector('strong[data-e2e="like-count"]');
                const commentCount = document.querySelector('strong[data-e2e="comment-count"]');
                
                return {
                    url: window.location.href,
                    description: descElement?.textContent || '',
                    username: usernameElement?.textContent || '',
                    videoSrc: videoElement?.src || '',
                    collectionTitle: collectionTitle?.textContent || '',
                    likes: likeCount?.textContent || '0',
                    comments: commentCount?.textContent || '0',
                    timestamp: new Date().toISOString()
                };
            }''')
            
            videos.append(video_info)
            print(f"\nCaptured video {len(videos)}: {video_info['url']}")

            # Check if "Next video" button exists
            has_next = await page.evaluate('''() => {
                return !!document.querySelector('button[data-e2e="arrow-right"]');
            }''')
            
            if not has_next:
                print("\nReached end of collection!")
                break

            # Press down arrow key to go to next video
            await page.keyboard.press('ArrowDown')
            await asyncio.sleep(2)  # Wait for next video to load

        return videos, {'title': videos[0]['collectionTitle'], 'totalVideos': str(len(videos))}

    except Exception as e:
        print(f"Error in handle_collection_videos: {str(e)}")
        return [], None

async def main():
    display_welcome_message()
    first_video_url = input("\nEnter TikTok Favorites collection first video URL: ").strip()
    
    try:
        browser, page = await setup_browser()
        print("Browser setup complete!")
        
        videos, collection_info = await handle_collection_videos(page, first_video_url)
        
        if not videos:
            print("No videos were captured!")
            return
            
        # Create backup directory with collection info
        collection_name = collection_info['title']
        sanitized_name = ''.join(c for c in collection_name if c.isalnum() or c in (' ', '-', '_'))
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            f"backup_{sanitized_name}_{timestamp}"
        )
        os.makedirs(backup_dir, exist_ok=True)
        print(f"\nCreated backup directory: {backup_dir}")
        
        # Save collection info
        collection_metadata = {
            'title': collection_info['title'],
            'total_videos': collection_info['totalVideos'],
            'backup_date': timestamp,
            'video_count': len(videos)
        }
        
        with open(os.path.join(backup_dir, 'collection_info.json'), 'w', encoding='utf-8') as f:
            json.dump(collection_metadata, f, ensure_ascii=False, indent=2)
        
        # Process and save videos
        for idx, video in enumerate(videos, 1):
            print(f"\nProcessing video {idx}/{len(videos)}")
            
            # Save video metadata
            metadata_path = os.path.join(backup_dir, f'video_{idx}_metadata.json')
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(video, f, ensure_ascii=False, indent=2)
            
            # Download video if available
            if video['videoSrc']:
                video_path = os.path.join(backup_dir, f'video_{idx}.mp4')
                await download_file(page, video['videoSrc'], video_path)
            
            await asyncio.sleep(1)
        
        print(f"\nBackup complete! Saved {len(videos)} videos from collection: {collection_info['title']}")
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        if 'browser' in locals():
            await browser.close()

if __name__ == "__main__":
    # Create new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close() 