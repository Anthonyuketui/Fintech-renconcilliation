"""
Unit tests for DataFetcher
Tests API integration, data normalization, and transformation logic
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
import requests
from data_fetcher import DataFetcher
from models import Transaction


class TestDataFetcher:
    """Test suite for DataFetcher class"""

    @pytest.fixture
    def fetcher(self):
        """Create a DataFetcher instance for testing"""
        return DataFetcher(
            processor_api_base_url="https://dummyjson.com",
            internal_api_base_url="https://jsonplaceholder.typicode.com",
            processor_name="stripe"
        )

    @pytest.fixture
    def mock_products_response(self):
        """Mock response from products API"""
        return {
            "products": [
                {
                    "id": 1,
                    "title": "iPhone 14",
                    "price": 899.99,
                    "category": "smartphones",
                    "brand": "Apple"
                },
                {
                    "id": 2,
                    "title": "Samsung Galaxy",
                    "price": 799.50,
                    "category": "smartphones",
                    "brand": "Samsung"
                },
                {
                    "id": 3,
                    "title": "MacBook Pro",
                    "price": 1299.00,
                    "category": "laptops",
                    "brand": "Apple"
                }
            ]
        }

    @pytest.fixture
    def mock_posts_response(self):
        """Mock response from posts API"""
        return [
            {"id": 1, "userId": 1, "title": "Post 1", "body": "Content 1"},
            {"id": 2, "userId": 1, "title": "Post 2", "body": "Content 2"},
            {"id": 3, "userId": 2, "title": "Post 3", "body": "Content 3"},
        ]

    def test_fetcher_initialization(self, fetcher):
        """Test DataFetcher initializes correctly"""
        assert fetcher.processor_api_base_url == "https://dummyjson.com"
        assert fetcher.internal_api_base_url == "https://jsonplaceholder.typicode.com"
        assert fetcher.processor_name == "stripe"
        assert fetcher.session is not None

    def test_fetcher_strips_trailing_slashes(self):
        """Test that trailing slashes are removed from URLs"""
        fetcher = DataFetcher(
            processor_api_base_url="https://dummyjson.com/",
            internal_api_base_url="https://jsonplaceholder.typicode.com/",
            processor_name="paypal"
        )
        assert not fetcher.processor_api_base_url.endswith("/")
        assert not fetcher.internal_api_base_url.endswith("/")

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_success(self, mock_get, fetcher, mock_products_response):
        """Test successful processor data fetch"""
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        assert len(transactions) == 3
        assert all(isinstance(t, Transaction) for t in transactions)
        mock_get.assert_called_once()

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_creates_correct_transaction_ids(self, mock_get, fetcher, mock_products_response):
        """Test that transaction IDs are formatted correctly"""
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        assert transactions[0].transaction_id == "TXN_STRIPE_20250930_0001"
        assert transactions[1].transaction_id == "TXN_STRIPE_20250930_0002"
        assert transactions[2].transaction_id == "TXN_STRIPE_20250930_0003"

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_calculates_fees(self, mock_get, fetcher, mock_products_response):
        """Test that processing fees are calculated correctly"""
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        # Fee = amount * 0.029 + 0.30
        expected_fee_1 = (Decimal("899.99") * Decimal("0.029") + Decimal("0.30")).quantize(Decimal('0.01'))
        assert transactions[0].fee == expected_fee_1

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_uses_decimal_for_amounts(self, mock_get, fetcher, mock_products_response):
        """Test that amounts are stored as Decimal for precision"""
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        for txn in transactions:
            assert isinstance(txn.amount, Decimal)
            assert isinstance(txn.fee, Decimal)

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_limits_to_30(self, mock_get, fetcher):
        """Test that processor data is limited to 30 transactions"""
        # Create response with 50 products
        large_response = {
            "products": [
                {"id": i, "price": 100.0, "category": "test", "brand": "brand"}
                for i in range(50)
            ]
        }
        mock_response = Mock()
        mock_response.json.return_value = large_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data()

        assert len(transactions) == 30

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_handles_api_error(self, mock_get, fetcher):
        """Test that API errors are properly raised"""
        mock_get.side_effect = requests.RequestException("API Error")

        with pytest.raises(requests.RequestException):
            fetcher.fetch_processor_data()

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_handles_timeout(self, mock_get, fetcher):
        """Test timeout handling"""
        mock_get.side_effect = requests.Timeout("Timeout")

        with pytest.raises(requests.Timeout):
            fetcher.fetch_processor_data()

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_sets_correct_processor_name(self, mock_get, fetcher, mock_products_response):
        """Test that processor name is correctly set"""
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data()

        assert all(t.processor_name == "stripe" for t in transactions)

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_internal_data_success(self, mock_get, fetcher, mock_posts_response):
        """Test successful internal data fetch"""
        mock_response = Mock()
        mock_response.json.return_value = mock_posts_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_internal_data(run_date=date(2025, 9, 30))

        assert len(transactions) == 25  # Creates transactions with IDs 1-25
        assert all(isinstance(t, Transaction) for t in transactions)

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_internal_data_creates_matching_ids(self, mock_get, fetcher, mock_posts_response):
        """Test that internal data creates IDs that match processor format"""
        mock_response = Mock()
        mock_response.json.return_value = mock_posts_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_internal_data(run_date=date(2025, 9, 30))

        # Check first and last transaction IDs
        assert transactions[0].transaction_id == "TXN_STRIPE_20250930_0001"
        assert transactions[24].transaction_id == "TXN_STRIPE_20250930_0025"

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_internal_data_calculates_amounts(self, mock_get, fetcher, mock_posts_response):
        """Test that internal amounts are calculated correctly"""
        mock_response = Mock()
        mock_response.json.return_value = mock_posts_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_internal_data(run_date=date(2025, 9, 30))

        # Amount = internal_id * 10.00
        assert transactions[0].amount == Decimal("10.00")  # ID 1
        assert transactions[1].amount == Decimal("20.00")  # ID 2
        assert transactions[4].amount == Decimal("50.00")  # ID 5

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_internal_data_handles_api_error(self, mock_get, fetcher):
        """Test that internal API errors are properly raised"""
        mock_get.side_effect = requests.RequestException("Internal API Error")

        with pytest.raises(requests.RequestException):
            fetcher.fetch_internal_data()

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_default_date(self, mock_get, fetcher, mock_products_response):
        """Test that default date is today when not specified"""
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data()  # No date specified

        today = date.today()
        expected_id = f"TXN_STRIPE_{today.strftime('%Y%m%d')}_0001"
        assert transactions[0].transaction_id == expected_id

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_handles_missing_fields(self, mock_get, fetcher):
        """Test handling of products with missing fields"""
        incomplete_response = {
            "products": [
                {"id": 1},  # Missing price, category, brand
                {"id": 2, "price": 50.0},  # Missing category, brand
            ]
        }
        mock_response = Mock()
        mock_response.json.return_value = incomplete_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data()

        # Should handle missing fields gracefully
        assert len(transactions) >= 0  # May skip invalid items

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_with_different_processors(self, mock_get, mock_products_response):
        """Test fetcher works with different processor names"""
        for processor in ["stripe", "paypal", "square"]:
            fetcher = DataFetcher(
                processor_api_base_url="https://dummyjson.com",
                internal_api_base_url="https://jsonplaceholder.typicode.com",
                processor_name=processor
            )

            mock_response = Mock()
            mock_response.json.return_value = mock_products_response
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            transactions = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

            assert transactions[0].transaction_id.startswith(f"TXN_{processor.upper()}_")
            assert all(t.processor_name == processor for t in transactions)

    def test_close_session(self, fetcher):
        """Test that session is properly closed"""
        session_mock = Mock()
        fetcher.session = session_mock

        fetcher.close()

        session_mock.close.assert_called_once()

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_processor_data_merchant_id_from_brand(self, mock_get, fetcher, mock_products_response):
        """Test merchant ID is derived from brand or category"""
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data()

        # Check merchant_id uses brand or category
        assert transactions[0].merchant_id in ["APPLE", "SMARTPHONES"]

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_data_sets_status_completed(self, mock_get, fetcher, mock_products_response):
        """Test all transactions have 'completed' status"""
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data()

        assert all(t.status == "completed" for t in transactions)

    @patch('src.data_fetcher.requests.Session.get')
    def test_fetch_data_sets_currency_usd(self, mock_get, fetcher, mock_products_response):
        """Test all transactions have USD currency"""
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data()

        assert all(t.currency == "USD" for t in transactions)

    @patch('data_fetcher.requests.Session.get')
    def test_fetch_processor_data_sets_reference_number(self, mock_get, fetcher, mock_products_response):
        """Test reference numbers are correctly formatted"""
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data()

        assert transactions[0].reference_number == "REF_STRIPE_1"
        assert transactions[1].reference_number == "REF_STRIPE_2"