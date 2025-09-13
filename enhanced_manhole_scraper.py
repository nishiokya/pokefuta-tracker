#!/usr/bin/env python3
"""
Enhanced Pokemon Manhole Cover Scraper
Scrapes detailed manhole cover data including location, address, name, and URL
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import os
import time
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional
import concurrent.futures
from threading import Lock

class EnhancedPokemonManholeScraper:
    def __init__(self, max_workers=5):
        self.base_url = "https://local.pokemon.jp/manhole/"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.max_workers = max_workers
        self.manhole_data = []
        self.lock = Lock()
        
    def get_page_content(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a webpage"""
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def extract_manhole_details(self, detail_url: str) -> Dict:
        """Extract detailed information from a manhole detail page"""
        print(f"Fetching details from: {detail_url}")
        soup = self.get_page_content(detail_url)
        
        if not soup:
            return {}
        
        manhole_info = {
            'url': detail_url,
            'name': '',
            'location': '',
            'address': '',
            'prefecture': '',
            'city': '',
            'coordinates': {},
            'pokemon': [],
            'description': '',
            'images': [],
            'installation_date': '',
            'design_info': {}
        }
        
        # Extract title/name
        title_elem = soup.find(['h1', 'h2', 'title'])
        if title_elem:
            manhole_info['name'] = title_elem.get_text(strip=True)
        
        # Extract location information
        location_elements = soup.find_all(text=re.compile(r'県|市|町|村'))
        for elem in location_elements:
            text = elem.strip()
            if '県' in text and '市' in text:
                manhole_info['location'] = text
                # Parse prefecture and city
                parts = text.split('県')
                if len(parts) > 1:
                    manhole_info['prefecture'] = parts[0] + '県'
                    city_part = parts[1].split('市')[0] + '市' if '市' in parts[1] else parts[1]
                    manhole_info['city'] = city_part
        
        # Extract address
        address_patterns = [
            r'住所[：:]?\s*(.+?)(?:\n|<|$)',
            r'所在地[：:]?\s*(.+?)(?:\n|<|$)',
            r'設置場所[：:]?\s*(.+?)(?:\n|<|$)'
        ]
        
        page_text = soup.get_text()
        for pattern in address_patterns:
            match = re.search(pattern, page_text)
            if match:
                manhole_info['address'] = match.group(1).strip()
                break
        
        # Extract Pokemon information
        pokemon_elements = soup.find_all(['img', 'span', 'div'], alt=re.compile(r'ポケモン|Pokemon', re.I))
        pokemon_names = set()
        
        for elem in pokemon_elements:
            if elem.get('alt'):
                pokemon_names.add(elem['alt'])
            if elem.get_text():
                # Look for Pokemon names in text
                pokemon_text = elem.get_text(strip=True)
                if any(char in pokemon_text for char in ['ポケモン', 'Pokemon']):
                    pokemon_names.add(pokemon_text)
        
        manhole_info['pokemon'] = list(pokemon_names)
        
        # Extract images
        images = soup.find_all('img')
        for img in images:
            if img.get('src') and 'manhole' in img.get('src', ''):
                img_info = {
                    'src': urljoin(self.base_url, img['src']),
                    'alt': img.get('alt', ''),
                    'title': img.get('title', '')
                }
                manhole_info['images'].append(img_info)
        
        # Extract description
        desc_elements = soup.find_all(['p', 'div'], class_=re.compile(r'desc|description|content'))
        descriptions = []
        for elem in desc_elements:
            text = elem.get_text(strip=True)
            if len(text) > 20:  # Filter out short texts
                descriptions.append(text)
        
        if descriptions:
            manhole_info['description'] = ' '.join(descriptions)
        
        # Extract coordinates if available
        coord_script = soup.find('script', text=re.compile(r'lat|lng|latitude|longitude'))
        if coord_script:
            script_text = coord_script.get_text()
            lat_match = re.search(r'lat[itude]*["\']?\s*[:=]\s*([0-9.-]+)', script_text)
            lng_match = re.search(r'lng|lon[gitude]*["\']?\s*[:=]\s*([0-9.-]+)', script_text)
            
            if lat_match and lng_match:
                manhole_info['coordinates'] = {
                    'latitude': float(lat_match.group(1)),
                    'longitude': float(lng_match.group(1))
                }
        
        return manhole_info
    
    def extract_main_page_manholes(self) -> List[Dict]:
        """Extract manhole links from the main page"""
        print("Extracting manhole links from main page...")
        soup = self.get_page_content(self.base_url)
        
        if not soup:
            return []
        
        manhole_links = []
        
        # Find all manhole detail links
        links = soup.find_all('a', href=re.compile(r'/manhole/desc/\d+/'))
        
        for link in links:
            href = link.get('href')
            text = link.get_text(strip=True)
            
            if href:
                full_url = urljoin(self.base_url, href)
                # Remove modal parameter for direct access
                full_url = full_url.replace('?is_modal=1', '')
                
                manhole_links.append({
                    'url': full_url,
                    'text': text,
                    'id': re.search(r'/desc/(\d+)/', href).group(1) if re.search(r'/desc/(\d+)/', href) else None
                })
        
        # Remove duplicates
        seen = set()
        unique_links = []
        for link in manhole_links:
            if link['url'] not in seen:
                seen.add(link['url'])
                unique_links.append(link)
        
        print(f"Found {len(unique_links)} unique manhole detail pages")
        return unique_links
    
    def extract_regional_manholes(self, regional_urls: List[str]) -> List[Dict]:
        """Extract manhole links from regional pages"""
        all_links = []
        
        for region_url in regional_urls:
            print(f"Extracting manholes from region: {region_url}")
            soup = self.get_page_content(region_url)
            
            if not soup:
                continue
            
            links = soup.find_all('a', href=re.compile(r'/manhole/desc/\d+/'))
            
            for link in links:
                href = link.get('href')
                text = link.get_text(strip=True)
                
                if href:
                    full_url = urljoin(self.base_url, href.replace('?is_modal=1', ''))
                    all_links.append({
                        'url': full_url,
                        'text': text,
                        'id': re.search(r'/desc/(\d+)/', href).group(1) if re.search(r'/desc/(\d+)/', href) else None,
                        'region_url': region_url
                    })
        
        # Remove duplicates
        seen = set()
        unique_links = []
        for link in all_links:
            if link['url'] not in seen:
                seen.add(link['url'])
                unique_links.append(link)
        
        return unique_links
    
    def scrape_manhole_details_parallel(self, manhole_links: List[Dict]) -> List[Dict]:
        """Scrape manhole details using parallel processing"""
        print(f"Scraping details for {len(manhole_links)} manholes...")
        
        detailed_manholes = []
        
        def scrape_single_manhole(link_info):
            time.sleep(0.5)  # Rate limiting
            details = self.extract_manhole_details(link_info['url'])
            details.update({
                'id': link_info.get('id'),
                'link_text': link_info.get('text'),
                'region_url': link_info.get('region_url')
            })
            
            with self.lock:
                detailed_manholes.append(details)
                print(f"Scraped: {details.get('name', 'Unknown')} ({len(detailed_manholes)}/{len(manhole_links)})")
            
            return details
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(scrape_single_manhole, link) for link in manhole_links]
            concurrent.futures.wait(futures)
        
        return detailed_manholes
    
    def get_regional_urls(self) -> List[str]:
        """Get regional page URLs"""
        soup = self.get_page_content(self.base_url)
        if not soup:
            return []
        
        regional_urls = []
        links = soup.find_all('a', href=re.compile(r'/manhole/area/\d+/'))
        
        for link in links:
            href = link.get('href')
            if href:
                regional_urls.append(urljoin(self.base_url, href))
        
        return list(set(regional_urls))  # Remove duplicates
    
    def save_data(self, data: List[Dict], filename: str = 'detailed_manhole_data.json'):
        """Save scraped data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Data saved to {filename}")
    
    def run_enhanced_scraper(self, scrape_regional=True, download_images=False):
        """Run the complete enhanced scraping process"""
        print("Starting Enhanced Pokemon Manhole Cover Scraper...")
        
        # Get manhole links from main page
        main_links = self.extract_main_page_manholes()
        
        all_links = main_links
        
        # Optionally scrape regional pages for more comprehensive data
        if scrape_regional:
            regional_urls = self.get_regional_urls()
            print(f"Found {len(regional_urls)} regional pages")
            regional_links = self.extract_regional_manholes(regional_urls)
            
            # Combine and deduplicate
            all_urls = set([link['url'] for link in all_links])
            for link in regional_links:
                if link['url'] not in all_urls:
                    all_links.append(link)
        
        print(f"Total unique manholes to scrape: {len(all_links)}")
        
        # Scrape detailed information
        detailed_manholes = self.scrape_manhole_details_parallel(all_links)
        
        # Save data
        self.save_data(detailed_manholes)
        
        # Download images if requested
        if download_images:
            self.download_all_images(detailed_manholes)
        
        # Print summary
        print(f"\nScraping completed!")
        print(f"- Total manholes scraped: {len(detailed_manholes)}")
        print(f"- Manholes with addresses: {sum(1 for m in detailed_manholes if m.get('address'))}")
        print(f"- Manholes with coordinates: {sum(1 for m in detailed_manholes if m.get('coordinates'))}")
        print(f"- Manholes with Pokemon info: {sum(1 for m in detailed_manholes if m.get('pokemon'))}")
        
        return detailed_manholes
    
    def download_all_images(self, manhole_data: List[Dict], download_dir: str = 'detailed_manhole_images'):
        """Download all manhole images"""
        os.makedirs(download_dir, exist_ok=True)
        
        all_images = []
        for manhole in manhole_data:
            for img in manhole.get('images', []):
                if img.get('src'):
                    all_images.append(img['src'])
        
        print(f"Downloading {len(all_images)} images...")
        for i, url in enumerate(all_images):
            try:
                response = self.session.get(url)
                response.raise_for_status()
                
                filename = os.path.basename(urlparse(url).path) or f"image_{i}.png"
                filepath = os.path.join(download_dir, filename)
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                if i % 10 == 0:  # Progress update every 10 images
                    print(f"Downloaded {i+1}/{len(all_images)} images")
                
                time.sleep(0.3)  # Rate limiting
                
            except Exception as e:
                print(f"Error downloading {url}: {e}")

def main():
    """Main function"""
    scraper = EnhancedPokemonManholeScraper(max_workers=3)  # Conservative threading
    
    try:
        manhole_data = scraper.run_enhanced_scraper(
            scrape_regional=True,
            download_images=False  # Set to True if you want to download images
        )
        
        # Show some sample data
        if manhole_data:
            print("\nSample manhole data:")
            sample = manhole_data[0]
            for key, value in sample.items():
                if isinstance(value, list) and len(value) > 3:
                    print(f"  {key}: [{len(value)} items]")
                elif isinstance(value, str) and len(value) > 100:
                    print(f"  {key}: {value[:100]}...")
                else:
                    print(f"  {key}: {value}")
                    
    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
    except Exception as e:
        print(f"Error during scraping: {e}")

if __name__ == "__main__":
    main()