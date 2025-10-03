# tests/test_data_fetcher.py

from __future__ import annotations
import sys
from pathlib import Path
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch
import pytest
import requests

# Ensure src can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))
from data_fetcher import DataFetcher
from models import Transaction


class TestDataFetcher:
    # -------------------------------
    # Fixtures
    # -------------------------------
    @pytest.fixture
    def fetcher(self):
        """Initialize a DataFetcher instance for tests."""
        return DataFetcher(
            processor_api_base_url="https://dummyjson.com",
            internal_api_base_url="https://jsonplaceholder.typicode.com",
            processor_name="stripe",
        )

    @pytest.fixture
    def mock_products_response(self):
        """Simulate processor API response with sample products."""
        return {
            "products": [
                {"id": 1, "title": "iPhone 14", "price": 899.99, "category": "smartphones", "brand": "Apple"},
                {"id": 2, "title": "Samsung Galaxy", "price": 799.50, "category": "smartphones", "brand": "Samsung"},
                {"id": 3, "title": "MacBook Pro", "price": 1299.00, "category": "laptops", "brand": "Apple"},
            ]
        }

    @pytest.fixture
    def mock_posts_response(self):
        """Simulate internal API response with sample posts."""
        return [
            {"id": 1, "userId": 1, "title": "Post 1", "body": "Content 1"},
            {"id": 2, "userId": 1, "title": "Post 2", "body": "Content 2"},
            {"id": 3, "userId": 2, "title": "Post 3", "body": "Content 3"},
        ]

    # -------------------------------
    # Processor Data Tests
    # -------------------------------
    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_success(self, mock_get, fetcher, mock_products_response):
        """
        Validates that processor data fetch returns Transaction objects with expected fields.
        """
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        assert all(isinstance(t, Transaction) for t in transactions)
        assert transactions[0].transaction_id.startswith("TXN_STRIPE_")
        assert transactions[0].processor_name == "stripe"
        assert all(t.status == "completed" for t in transactions)
        assert all(t.currency == "USD" for t in transactions)
        assert transactions[0].reference_number.startswith("REF_STRIPE_")

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_calculates_fees(self, mock_get, fetcher, mock_products_response):
        """
        Validates that fees are correctly calculated per transaction.
        """
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        for txn in transactions:
            expected_fee = (txn.amount * Decimal("0.029") + Decimal("0.30")).quantize(Decimal("0.01"))
            assert txn.fee == expected_fee
            assert isinstance(txn.amount, Decimal)
            assert isinstance(txn.fee, Decimal)

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_limits_to_30(self, mock_get, fetcher):
        """
        Ensures that fetch_processor_data does not return more than 30 transactions.
        """
        large_response = {"products": [{"id": i, "price": 100.0, "category": "test", "brand": "brand"} for i in range(50)]}
        mock_response = Mock()
        mock_response.json.return_value = large_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data()
        assert len(transactions) == min(30, len(large_response["products"]))

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_handles_api_error(self, mock_get, fetcher):
        """Validates that a RequestException is propagated if API fails."""
        mock_get.side_effect = requests.RequestException("API Error")
        with pytest.raises(requests.RequestException):
            fetcher.fetch_processor_data()

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_handles_timeout(self, mock_get, fetcher):
        """Validates that a Timeout is propagated if API times out."""
        mock_get.side_effect = requests.Timeout("Timeout")
        with pytest.raises(requests.Timeout):
            fetcher.fetch_processor_data()

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_trailing_slashes(self, mock_get):
        """
        Ensures base URLs are normalized (no trailing slashes).
        """
        fetcher = DataFetcher(
            processor_api_base_url="https://dummyjson.com/",
            internal_api_base_url="https://jsonplaceholder.typicode.com/",
            processor_name="paypal",
        )
        assert not fetcher.processor_api_base_url.endswith("/")
        assert not fetcher.internal_api_base_url.endswith("/")

    # -------------------------------
    # Internal Data Tests
    # -------------------------------
    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_internal_data_success(self, mock_get, fetcher, mock_posts_response, mock_products_response):
        """
        Validates that internal data fetch returns Transaction objects derived from processor data.
        """
        processor_mock = Mock()
        processor_mock.json.return_value = mock_products_response
        processor_mock.raise_for_status = Mock()
        mock_get.return_value = processor_mock
        processor_txns = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        posts_mock = Mock()
        posts_mock.json.return_value = mock_posts_response
        posts_mock.raise_for_status = Mock()
        mock_get.return_value = posts_mock
        internal_txns = fetcher.fetch_internal_data(processor_txns=processor_txns, run_date=date(2025, 9, 30))

        assert len(internal_txns) >= 1
        assert all(isinstance(t, Transaction) for t in internal_txns)

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_internal_data_calculates_amounts(self, mock_get, fetcher, mock_posts_response, mock_products_response):
        """
        Validates that internal transactions amounts are consistent with processor transaction amounts.
        """
        processor_mock = Mock()
        processor_mock.json.return_value = mock_products_response
        processor_mock.raise_for_status = Mock()
        mock_get.return_value = processor_mock
        processor_txns = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        posts_mock = Mock()
        posts_mock.json.return_value = mock_posts_response
        posts_mock.raise_for_status = Mock()
        mock_get.return_value = posts_mock
        internal_txns = fetcher.fetch_internal_data(processor_txns=processor_txns, run_date=date(2025, 9, 30))

        internal_amounts = {txn.amount for txn in internal_txns}
        processor_amounts = {txn.amount for txn in processor_txns}

        assert internal_amounts.issubset(processor_amounts)
        assert len(internal_txns) >= 1

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_internal_data_handles_api_error(self, mock_get, fetcher, mock_products_response):
        """
        Validates that internal API errors propagate as exceptions.
        """
        processor_mock = Mock()
        processor_mock.json.return_value = mock_products_response
        processor_mock.raise_for_status = Mock()
        mock_get.return_value = processor_mock
        processor_txns = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        mock_get.side_effect = requests.RequestException("Internal API Error")
        with pytest.raises(requests.RequestException):
            fetcher.fetch_internal_data(processor_txns=processor_txns)

    # -------------------------------
    # Misc / Logic Tests
    # -------------------------------
    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_merchant_id_logic(self, mock_get, fetcher, mock_products_response):
        """
        Ensures merchant_id is correctly assigned based on processor data logic.
        """
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        transactions = fetcher.fetch_processor_data()

        assert all(
            t.merchant_id.startswith("MERCH_")
            or t.merchant_id in ["APPLE", "SMARTPHONES", "SAMSUNG", "LAPTOPS"]
            for t in transactions
        )

    def test_close_session(self, fetcher):
        """
        Validates that the fetcher's requests session is closed properly.
        """
        session_mock = Mock()
        fetcher.session = session_mock
        fetcher.close()
        session_mock.close.assert_called_once()
