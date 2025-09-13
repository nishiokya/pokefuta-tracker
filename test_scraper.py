#!/usr/bin/env python3
"""
Quick test of the Pokemon manhole scraper
"""

from pokemon_manhole_scraper import PokemonManholeScraper

def main():
    scraper = PokemonManholeScraper()
    
    # Test just the main page scraping without image downloads
    print("Testing main page scraping...")
    main_data = scraper.scrape_main_page()
    
    # Save data
    scraper.save_data(main_data, 'test_manhole_data.json')
    
    # Print results
    print(f"Found {main_data.get('total_manholes_found', 0)} manhole entries")
    
    js_data = main_data.get('javascript_data', {})
    if js_data.get('images'):
        print(f"Found {len(js_data['images'])} image URLs")
        print("Sample images:", js_data['images'][:5])
    
    if main_data.get('regional_links'):
        print(f"Found {len(main_data['regional_links'])} regional links")

if __name__ == "__main__":
    main()