#!/usr/bin/env python3
"""Tests for ImmoWeb scraper logic (uses mocked HTTP responses)."""

import json
import unittest
from unittest.mock import patch, MagicMock
from ImmoCollecterImmoWeb import ImmoWeb
from ImmoCollecterTools import ImmoCollecterTools


class TestImmoWebURLConversion(unittest.TestCase):
    """Test URL conversion from search to API format."""

    def test_nl_url_conversion(self):
        url = "https://www.immoweb.be/nl/zoeken/huis/te-koop?countries=BE&page=1"
        result = ImmoWeb._convert_to_api_url(url)
        self.assertIn("/nl/search-results/", result)
        self.assertNotIn("/nl/zoeken/", result)

    def test_en_url_conversion(self):
        url = "https://www.immoweb.be/en/search/house/for-sale?countries=BE"
        result = ImmoWeb._convert_to_api_url(url)
        self.assertIn("/en/search-results/", result)
        self.assertNotIn("/en/search/", result)

    def test_fr_url_conversion(self):
        url = "https://www.immoweb.be/fr/recherche/maison/a-vendre?countries=BE"
        result = ImmoWeb._convert_to_api_url(url)
        self.assertIn("/fr/search-results/", result)


class TestImmoCollecterTools(unittest.TestCase):
    """Test the data extraction tools."""

    def test_extract_simple_key(self):
        data = {'id': 12345}
        result = ImmoCollecterTools._get_data_from_tree(['id'], data)
        self.assertEqual(result, 12345)

    def test_extract_nested_key(self):
        data = {'price': {'mainValue': 500000}}
        result = ImmoCollecterTools._get_data_from_tree(['price', 'mainValue'], data)
        self.assertEqual(result, 500000)

    def test_extract_missing_key(self):
        data = {'price': {'mainValue': 500000}}
        result = ImmoCollecterTools._get_data_from_tree(['price', 'oldValue'], data)
        self.assertIsNone(result)

    def test_extract_deeply_nested(self):
        data = {'property': {'building': {'condition': 'GOOD'}}}
        result = ImmoCollecterTools._get_data_from_tree(['property', 'building', 'condition'], data)
        self.assertEqual(result, 'GOOD')

    def test_extract_with_list_index(self):
        data = {'customers': [{'id': 999, 'type': 'AGENCY'}]}
        result = ImmoCollecterTools._get_data_from_tree(['customers', 0, 'id'], data)
        self.assertEqual(result, 999)

    def test_extract_data_house(self):
        house = {
            'id': 12345,
            'price': {'mainValue': 350000, 'type': 'residential_sale'},
            'property': {
                'title': 'Nice house',
                'bedroomCount': 3,
                'location': {'postalCode': '9000', 'locality': 'Gent'},
            }
        }
        conversion = {
            'id': ['id'],
            'price_main': ['price', 'mainValue'],
            'title': ['property', 'title'],
            'bedrooms': ['property', 'bedroomCount'],
            'postalcode': ['property', 'location', 'postalCode'],
            'city': ['property', 'location', 'locality'],
        }
        result = ImmoCollecterTools.extract_data_house(house, conversion)
        self.assertEqual(result['id'], 12345)
        self.assertEqual(result['price_main'], 350000)
        self.assertEqual(result['title'], 'Nice house')
        self.assertEqual(result['bedrooms'], 3)
        self.assertEqual(result['postalcode'], '9000')
        self.assertEqual(result['city'], 'Gent')


MOCK_CLASSIFIED_DATA = {
    'id': 10001,
    'customers': [{'id': 555, 'type': 'AGENCY'}],
    'price': {'mainValue': 425000, 'oldValue': None, 'type': 'residential_sale'},
    'property': {
        'title': 'Mooie woning met tuin',
        'description': 'Een prachtige woning...',
        'netHabitableSurface': 180,
        'bedroomCount': 4,
        'bathroomCount': 1,
        'showerRoomCount': 1,
        'parkingCountIndoor': 1,
        'parkingCountOutdoor': 0,
        'livingRoom': {'surface': 45},
        'building': {'condition': 'GOOD', 'constructionYear': '1995'},
        'land': {'surface': 800},
        'location': {'postalCode': '9000', 'locality': 'Gent', 'street': 'Teststraat', 'number': '42'},
        'type': 'HOUSE',
        'subtype': 'VILLA',
    },
    'publication': {
        'creationDate': '2024-01-15T10:00:00.000+0000',
        'expirationDate': '2024-04-15T10:00:00.000+0000',
        'lastModificationDate': '2024-02-01T14:30:00.657+0000',
    },
    'transaction': {
        'certificates': {'epcScore': 'B', 'primaryEnergyConsumptionPerSqm': 150},
    },
    'media': {
        'pictures': [
            {'largeUrl': 'https://example.com/pic1.jpg', 'smallUrl': 'https://example.com/pic1_s.jpg'},
            {'largeUrl': 'https://example.com/pic2.jpg', 'smallUrl': 'https://example.com/pic2_s.jpg'},
        ]
    },
}

MOCK_SEARCH_API_RESPONSE = {
    'totalItems': 45,
    'results': [
        {'id': 10001, 'property': {'type': 'HOUSE'}},
        {'id': 10002, 'property': {'type': 'HOUSE'}},
        {'id': 10003, 'property': {'type': 'HOUSE'}},
    ]
}


class TestImmoWebScraper(unittest.TestCase):
    """Test the ImmoWeb scraper with mocked HTTP responses."""

    def _make_classified_html(self, data):
        """Create a mock HTML page with window.classified data."""
        json_str = json.dumps(data)
        return f"""
        <html><body>
        <div class="classified">
            <script>
                window.classified = {json_str};
            </script>
        </div>
        </body></html>
        """

    @patch.object(ImmoWeb, '_request_url')
    def test_get_house_details(self, mock_request):
        """Test parsing of a property detail page."""
        mock_response = MagicMock()
        mock_response.text = self._make_classified_html(MOCK_CLASSIFIED_DATA)
        mock_request.return_value = mock_response

        immo = ImmoWeb("https://www.immoweb.be/nl/zoeken/huis/te-koop?countries=BE")
        result = immo.get_house_details({'id': 10001})

        self.assertIsNotNone(result)
        self.assertEqual(result['id'], 10001)
        self.assertEqual(result['price_main'], 425000)
        self.assertEqual(result['title'], 'Mooie woning met tuin')
        self.assertEqual(result['surface'], 180)
        self.assertEqual(result['bedrooms'], 4)
        self.assertEqual(result['bathrooms'], 2)  # 1 bathroom + 1 shower
        self.assertEqual(result['parking'], 1)  # 1 indoor + 0 outdoor
        self.assertEqual(result['postalcode'], '9000')
        self.assertEqual(result['city'], 'Gent')
        self.assertEqual(result['condition'], 'GOOD')
        self.assertEqual(result['epcScore'], 'B')
        self.assertEqual(result['lastModificationDate'], '2024-02-01T14:30:00')
        self.assertEqual(result['immoProvider'], 'immoweb')
        self.assertEqual(result['displayAd'], 1)
        self.assertIn('pic1.jpg', result['pictureUrls'])
        self.assertIn('pic2.jpg', result['pictureUrls'])
        self.assertEqual(len(result['pictureDownloads']), 2)

    @patch.object(ImmoWeb, '_request_url')
    def test_get_house_details_missing_ad(self, mock_request):
        """Test handling of a missing ad page."""
        mock_response = MagicMock()
        mock_response.text = "<html><body><div>Not found</div></body></html>"
        mock_request.return_value = mock_response

        immo = ImmoWeb("https://www.immoweb.be/nl/zoeken/huis/te-koop?countries=BE")
        result = immo.get_house_details({'id': 99999})
        self.assertIsNone(result)

    @patch.object(ImmoWeb, '_request_url')
    def test_get_house_details_none_response(self, mock_request):
        """Test handling of a failed HTTP request."""
        mock_request.return_value = None

        immo = ImmoWeb("https://www.immoweb.be/nl/zoeken/huis/te-koop?countries=BE")
        result = immo.get_house_details({'id': 99999})
        self.assertIsNone(result)

    @patch.object(ImmoWeb, '_request_url')
    def test_get_house_details_none_fields(self, mock_request):
        """Test handling of missing fields in classified data."""
        data = dict(MOCK_CLASSIFIED_DATA)
        data['property'] = dict(data['property'])
        data['property']['bathroomCount'] = None
        data['property']['showerRoomCount'] = None
        data['property']['parkingCountIndoor'] = None
        data['property']['parkingCountOutdoor'] = None
        data['publication'] = dict(data['publication'])
        data['publication']['lastModificationDate'] = None

        mock_response = MagicMock()
        mock_response.text = self._make_classified_html(data)
        mock_request.return_value = mock_response

        immo = ImmoWeb("https://www.immoweb.be/nl/zoeken/huis/te-koop?countries=BE")
        result = immo.get_house_details({'id': 10001})

        self.assertIsNotNone(result)
        self.assertEqual(result['bathrooms'], 0)
        self.assertEqual(result['parking'], 0)
        self.assertIsNotNone(result['lastModificationDate'])

    @patch.object(ImmoWeb, '_request_url')
    def test_get_list_from_api(self, mock_request):
        """Test fetching house list from JSON API (single page)."""
        single_page_response = {
            'totalItems': 3,
            'results': [
                {'id': 10001, 'property': {'type': 'HOUSE'}},
                {'id': 10002, 'property': {'type': 'HOUSE'}},
                {'id': 10003, 'property': {'type': 'HOUSE'}},
            ]
        }
        mock_response = MagicMock()
        mock_response.json.return_value = single_page_response
        mock_request.return_value = mock_response

        immo = ImmoWeb("https://www.immoweb.be/nl/zoeken/huis/te-koop?countries=BE")
        houses = immo._get_list_from_api()

        self.assertEqual(len(houses), 3)
        self.assertEqual(houses[0]['id'], 10001)

    @patch.object(ImmoWeb, '_request_url')
    def test_get_list_from_api_empty(self, mock_request):
        """Test handling of empty API response."""
        mock_request.return_value = None

        immo = ImmoWeb("https://www.immoweb.be/nl/zoeken/huis/te-koop?countries=BE")
        houses = immo._get_list_from_api()

        self.assertEqual(len(houses), 0)

    @patch.object(ImmoWeb, '_request_url')
    def test_get_total_houses_from_api(self, mock_request):
        """Test getting total house count from API."""
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_SEARCH_API_RESPONSE
        mock_request.return_value = mock_response

        immo = ImmoWeb("https://www.immoweb.be/nl/zoeken/huis/te-koop?countries=BE")
        total = immo._get_total_houses_api()

        self.assertEqual(total, 45)


class TestImmoWebIsHouseGone(unittest.TestCase):
    """Test the is_house_gone static method."""

    @patch('ImmoCollecterImmoWeb.requests.get')
    def test_house_exists(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = """
        <html><body>
        <script>window.classified = {"id": 123};</script>
        </body></html>
        """
        mock_get.return_value = mock_response

        self.assertFalse(ImmoWeb.is_house_gone("https://www.immoweb.be/nl/zoekertje/123"))

    @patch('ImmoCollecterImmoWeb.requests.get')
    def test_house_gone(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = "<html><body>Not found</body></html>"
        mock_get.return_value = mock_response

        self.assertTrue(ImmoWeb.is_house_gone("https://www.immoweb.be/nl/zoekertje/123"))

    @patch('ImmoCollecterImmoWeb.requests.get')
    def test_house_request_fails(self, mock_get):
        mock_get.side_effect = Exception("Connection error")
        self.assertTrue(ImmoWeb.is_house_gone("https://www.immoweb.be/nl/zoekertje/123"))


if __name__ == '__main__':
    unittest.main()
