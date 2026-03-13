from ImmoCollecterItf import ImmoCollecterItf
from ImmoCollecterTools import ImmoCollecterTools
import requests
from requests.exceptions import HTTPError
from bs4 import BeautifulSoup
import json
import re
import math
import datetime

CONVERSION_TABLE = {'id': ['id'],
    'customerId': ['customers', 0, 'id'],
    'customerType': ['customers', 0, 'type'],
    'price_main': ['price', 'mainValue'],
    'price_old': ['price', 'oldValue'],
    'price_type': ['price', 'type'],
    'title': ['property', 'title'],
    'description': ['property', 'description'],
    'surface': ['property', 'netHabitableSurface'],
    'bedrooms': ['property', 'bedroomCount'],
    'livingRoom': ['property', 'livingRoom'],
    'condition': ['property', 'building', 'condition'],
    'constructionYear' : ['property', 'building', 'constructionYear'],
    'landSurface': ['property', 'land', 'surface'],
    'postalcode': ['property', 'location','postalCode'],
    'city': ['property', 'location','locality'],
    'street': ['property', 'location', 'street'],
    'number': ['property', 'location', 'number'],
    'type': ['property', 'type'],'subtype': ['property', 'subtype'],
    'creationDate': ['publication', 'creationDate'],
    'expirationDate': ['publication', 'expirationDate'],
    'lastModificationDate': ['publication', 'lastModificationDate'],
    'epcScore': ['transaction', 'certificates', 'epcScore'],
    'primaryEnergyConsumptionPerSqm': ['transaction', 'certificates', 'primaryEnergyConsumptionPerSqm'],
    'bathroomCount': ['property', 'bathroomCount'],
    'showerRoomCount': ['property', 'showerRoomCount'],
    'parkingCountIndoor': ['property', 'parkingCountIndoor'],
    'parkingCountOutdoor': ['property', 'parkingCountOutdoor'],
    'livingRoom': ['property', 'livingRoom', 'surface'],
    'url' : ['url'],
    }

HEADERS = {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0'}

class ImmoWeb(ImmoCollecterItf):
    def __init__(self, search_url) -> None:
        self.conn = None
        self.search_url = search_url
        self._api_url = self._convert_to_api_url(search_url)
        self._create_connection()

    def _create_connection(self, headers=HEADERS):
        self.conn = requests.Session()
        self.conn.headers = headers

    @staticmethod
    def _convert_to_api_url(search_url):
        """Convert a regular ImmoWeb search URL to the search-results API URL.

        e.g. /nl/zoeken/huis/te-koop?... -> /nl/search-results/huis/te-koop?...
             /en/search/house/for-sale?... -> /en/search-results/house/for-sale?...
        """
        api_url = search_url.replace('/nl/zoeken/', '/nl/search-results/')
        api_url = api_url.replace('/en/search/', '/en/search-results/')
        api_url = api_url.replace('/fr/recherche/', '/fr/search-results/')
        return api_url

    def _request_url(self, url):
        response = None
        try:
            response = self.conn.get(url)
            response.raise_for_status()
        except HTTPError as http_err:
            print(f'HTTP error occured : {http_err}')
        except Exception as err:
            print(f'Other error occured : {err}')

        return response

    def _search_api(self, page=1):
        """Fetch search results from ImmoWeb's JSON API endpoint."""
        url = re.sub(r'[&?]page=\d+', '', self._api_url)
        separator = '&' if '?' in url else '?'
        url = f"{url}{separator}page={page}"

        response = self._request_url(url)
        if response is None:
            return None
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError) as err:
            print(f"Error: Could not parse JSON from search API: {err}")
            return None

    def _get_total_houses_api(self):
        """Get total house count from the JSON API."""
        data = self._search_api(page=1)
        if data is None:
            return -1
        return data.get('totalItems', -1)

    def _get_total_houses(self, url):
        """Get total house count. Tries JSON API first, falls back to HTML parsing."""
        # Try the JSON API first (more reliable)
        total = self._get_total_houses_api()
        if total > 0:
            return total

        # Fallback: parse HTML with iw-search component
        search_page = self._request_url(url)
        if search_page is None:
            print("Error: Failed to fetch search page.")
            return -1

        soup = BeautifulSoup(search_page.text, "html.parser")
        try:
            total_houses = json.loads(soup.find("iw-search")[":result-count"])
        except (TypeError, KeyError) as err:
            print("Error: No total announcements found. Please review the URL.")
            total_houses = -1

        return total_houses

    def _get_total_pages(self, url):
        try:
            total_pages = math.ceil(self._get_total_houses(url)/30)
        except TypeError as err:
            print("Error: No search page found. Please review the URL")
            total_pages = -1

        return total_pages

    def get_list_all_houses(self):
        """Get list of all houses from search results. Tries JSON API first, falls back to HTML."""
        # Try JSON API first
        houses = self._get_list_from_api()
        if houses:
            return houses

        # Fallback: HTML parsing with iw-search component
        print("API method failed, falling back to HTML parsing...")
        return self._get_list_from_html()

    def _get_list_from_api(self):
        """Get house list from ImmoWeb's search-results JSON API."""
        houses = []
        first_page = self._search_api(page=1)
        if first_page is None:
            return houses

        total_items = first_page.get('totalItems', 0)
        if total_items <= 0:
            return houses

        results = first_page.get('results', [])
        houses.extend(results)

        items_per_page = len(results) if results else 30
        total_pages = min(math.ceil(total_items / items_per_page), 8)

        for page in range(2, total_pages + 1):
            data = self._search_api(page=page)
            if data and 'results' in data:
                houses.extend(data['results'])

        print(f"Found {len(houses)} houses via API (total available: {total_items})")
        return houses

    def _get_list_from_html(self):
        """Fallback: get house list by parsing HTML with iw-search component."""
        total_pages = min(self._get_total_pages(self.search_url), 8)
        houses = []

        for page in range(1, total_pages + 1):
            url = self.search_url + '&page=' + str(page)
            search_page = self._request_url(url)
            if search_page is None:
                print(f"Error: Failed to fetch page {page}")
                continue
            soup = BeautifulSoup(search_page.text, "html.parser")
            try:
                houses.extend(json.loads(soup.find("iw-search")[":results"]))
            except (TypeError, KeyError) as err:
                print(f"Error: Could not parse results from page {page}")

        return houses

    def get_house_details(self, house_ref):
        # Return a json with all data from a specific classified
        URL_IMMO = "https://www.immoweb.be/nl/zoekertje/"
        house_url = URL_IMMO + str(house_ref['id'])
        print(house_url)
        house_page = self._request_url(house_url)
        if house_page is None:
            print(f'Failed to fetch ad page (ad = {house_ref["id"]})')
            return None
        soup = BeautifulSoup(house_page.text, "html.parser")

        house = None
        # Method 1: Look for window.classified in a script tag inside div.classified
        try:
            classified_div = soup.find("div", "classified")
            if classified_div:
                script = classified_div.find("script")
                if script and script.string and "window.classified" in script.string:
                    raw = script.string.split("window.classified = ")[1]
                    # Find the end of the JSON object
                    house = json.loads(raw.split(";\n")[0])
        except (AttributeError, IndexError, json.JSONDecodeError):
            pass

        # Method 2: Regex search across all script tags for window.classified
        if house is None:
            for script in soup.find_all("script"):
                if script.string and "window.classified" in script.string:
                    match = re.search(r'window\.classified\s*=\s*({.*?});\s*\n', script.string, re.DOTALL)
                    if match:
                        try:
                            house = json.loads(match.group(1))
                            break
                        except json.JSONDecodeError:
                            continue

        if house is None:
            print(f'Ad not found (ad = {house_ref["id"]})')
            return None

        normalized_house = ImmoCollecterTools.extract_data_house(house, CONVERSION_TABLE)
        normalized_house['bathrooms'] = (normalized_house['bathroomCount'] if normalized_house['bathroomCount'] is not None else 0) + (normalized_house['showerRoomCount'] if normalized_house['showerRoomCount'] is not None else 0)
        normalized_house['parking'] = (normalized_house['parkingCountIndoor'] if normalized_house['parkingCountIndoor'] is not None else 0) + (normalized_house['parkingCountOutdoor'] if normalized_house['parkingCountOutdoor'] is not None else 0)
        [normalized_house.pop(key) for key in ['bathroomCount', 'showerRoomCount', 'parkingCountIndoor', 'parkingCountOutdoor']]
        if normalized_house['lastModificationDate']:
            normalized_house['lastModificationDate'] = normalized_house['lastModificationDate'].split('.')[0]
        else:
            normalized_house['lastModificationDate'] = datetime.datetime.now().isoformat()

        pic_list = []
        pic_download = []
        if "media" in house:
            if "pictures" in house["media"]:
                for pic_item in house["media"]["pictures"]:
                    pic_list.append(pic_item['largeUrl'])
                    pic_download.append(pic_item['largeUrl'])
        normalized_house['pictureUrls'] = ",".join(pic_list)
        normalized_house['pictureDownloads'] = pic_download

        normalized_house["url"] = house_url
        normalized_house['lastSeen'] = datetime.datetime.now()
        normalized_house["displayAd"] = 1
        normalized_house['immoProvider'] = "immoweb"

        return normalized_house

    @staticmethod
    def is_house_gone(url):
        try:
            house_page = requests.get(url, headers=HEADERS)
            soup = BeautifulSoup(house_page.text, "html.parser")
            # Try the standard approach
            for script in soup.find_all("script"):
                if script.string and "window.classified" in script.string:
                    return False
            return True
        except:
            return True
