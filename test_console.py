import asyncio
from playwright.async_api import async_playwright
import time

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Catch console messages
        def handle_console(msg):
            print(f"[{msg.type}] {msg.text}")

        page.on("console", handle_console)
        
        # Load the page and search
        await page.goto("http://127.0.0.1:5000")
        await page.wait_for_selector("#query-input")
        await page.type("#query-input", "火")
        await page.click("#search-btn")
        
        print("Waiting for results...")
        await page.wait_for_timeout(3000)
        await browser.close()
        
if __name__ == "__main__":
    asyncio.run(main())
