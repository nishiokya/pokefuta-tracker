#!/usr/bin/env python3
"""
Test the enhanced Pokemon manhole scraper with a few sample manholes
"""

from enhanced_manhole_scraper import EnhancedPokemonManholeScraper
import time

def main():
    scraper = EnhancedPokemonManholeScraper(max_workers=2)  # Conservative for testing
    
    # Test with a few specific manhole detail URLs from the JSON data
    test_urls = [
        "https://local.pokemon.jp/manhole/desc/45/",
        "https://local.pokemon.jp/manhole/desc/188/", 
        "https://local.pokemon.jp/manhole/desc/232/"
    ]
    
    test_links = [
        {'url': url, 'text': f'Test {i+1}', 'id': url.split('/')[-2]} 
        for i, url in enumerate(test_urls)
    ]
    
    print(f"Testing enhanced scraper with {len(test_links)} manholes...")
    
    # Test detailed scraping
    detailed_manholes = scraper.scrape_manhole_details_parallel(test_links)
    
    # Save test results
    scraper.save_data(detailed_manholes, 'test_enhanced_results.json')
    
    # Print sample results
    print(f"\nTest completed! Scraped {len(detailed_manholes)} manholes")
    
    for i, manhole in enumerate(detailed_manholes[:2], 1):
        print(f"\nSample {i}:")
        print(f"  Name: {manhole.get('name', 'N/A')}")
        print(f"  Location: {manhole.get('location', 'N/A')}")
        print(f"  Address: {manhole.get('address', 'N/A')}")
        print(f"  Prefecture: {manhole.get('prefecture', 'N/A')}")
        print(f"  City: {manhole.get('city', 'N/A')}")
        print(f"  Pokemon: {manhole.get('pokemon', [])}")
        print(f"  Coordinates: {manhole.get('coordinates', {})}")
        print(f"  Images: {len(manhole.get('images', []))} found")
        print(f"  URL: {manhole.get('url', 'N/A')}")

if __name__ == "__main__":
    main()