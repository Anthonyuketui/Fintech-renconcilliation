from __future__ import annotations
import sys
from pathlib import Path
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch
from unittest.mock import MagicMock
import logging
import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from data_fetcher import DataFetcher
from models import Transaction


class TestDataFetcher:
    @pytest.fixture
    def fetcher(self):
        return DataFetcher(
            processor_api_base_url="https://dummyjson.com",
            internal_api_base_url="https://jsonplaceholder.typicode.com",
            processor_name="stripe",
        )

    @pytest.fixture
    def mock_products_response(self):
        return {
            "products": [
                {
                    "id": 1,
                    "title": "iPhone 14",
                    "price": 899.99,
                    "category": "smartphones",
                    "brand": "Apple",
                },
                {
                    "id": 2,
                    "title": "Samsung Galaxy",
                    "price": 799.50,
                    "category": "smartphones",
                    "brand": "Samsung",
                },
                {
                    "id": 3,
                    "title": "MacBook Pro",
                    "price": 1299.00,
                    "category": "laptops",
                    "brand": "Apple",
                },
            ]
        }

    @pytest.fixture
    def mock_posts_response(self):
        return [
            {"id": 1, "userId": 1, "title": "Post 1", "body": "Content 1"},
            {"id": 2, "userId": 1, "title": "Post 2", "body": "Content 2"},
            {"id": 3, "userId": 2, "title": "Post 3", "body": "Content 3"},
        ]

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_success(
        self, mock_get, fetcher, mock_products_response
    ):
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
    def test_fetch_processor_data_calculates_fees(
        self, mock_get, fetcher, mock_products_response
    ):
        mock_response = Mock()
        mock_response.json.return_value = mock_products_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        transactions = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        for txn in transactions:
            expected_fee = (txn.amount * Decimal("0.029") + Decimal("0.30")).quantize(
                Decimal("0.01")
            )
            assert txn.fee == expected_fee
            assert isinstance(txn.amount, Decimal)
            assert isinstance(txn.fee, Decimal)

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_paginates_and_fetches_all(self, mock_get, fetcher):
        page1 = {"products": [{"id": i, "price": 100.0} for i in range(30)]}
        page2 = {"products": [{"id": i + 30, "price": 100.0} for i in range(20)]}
        page3 = {"products": []}

        mock_responses = []
        for resp_data in [page1, page2, page3]:
            mock_resp = Mock()
            mock_resp.json.return_value = resp_data
            mock_resp.raise_for_status = Mock()
            mock_responses.append(mock_resp)

        mock_get.side_effect = mock_responses

        transactions = fetcher.fetch_processor_data()

        assert len(transactions) == 50

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_handles_api_error(self, mock_get, fetcher):
        mock_get.side_effect = requests.RequestException("API Error")
        with pytest.raises(requests.RequestException):
            fetcher.fetch_processor_data()

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_handles_timeout(self, mock_get, fetcher):
        mock_get.side_effect = requests.Timeout("Timeout")
        with pytest.raises(requests.Timeout):
            fetcher.fetch_processor_data()

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_trailing_slashes(self, mock_get):
        fetcher = DataFetcher(
            processor_api_base_url="https://dummyjson.com/",
            internal_api_base_url="https://jsonplaceholder.typicode.com/",
            processor_name="paypal",
        )
        assert not fetcher.processor_api_base_url.endswith("/")
        assert not fetcher.internal_api_base_url.endswith("/")

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_internal_data_success(
        self, mock_get, fetcher, mock_posts_response, mock_products_response
    ):
        processor_mock = Mock()
        processor_mock.json.return_value = mock_products_response
        processor_mock.raise_for_status = Mock()
        mock_get.return_value = processor_mock
        processor_txns = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        posts_mock = Mock()
        posts_mock.json.return_value = mock_posts_response
        posts_mock.raise_for_status = Mock()
        mock_get.return_value = posts_mock
        internal_txns = fetcher.fetch_internal_data(
            processor_txns=processor_txns, run_date=date(2025, 9, 30)
        )

        assert len(internal_txns) >= 1
        assert all(isinstance(t, Transaction) for t in internal_txns)

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_internal_data_calculates_amounts(
        self, mock_get, fetcher, mock_posts_response, mock_products_response
    ):
        processor_mock = Mock()
        processor_mock.json.return_value = mock_products_response
        processor_mock.raise_for_status = Mock()
        mock_get.return_value = processor_mock
        processor_txns = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        posts_mock = Mock()
        posts_mock.json.return_value = mock_posts_response
        posts_mock.raise_for_status = Mock()
        mock_get.return_value = posts_mock
        internal_txns = fetcher.fetch_internal_data(
            processor_txns=processor_txns, run_date=date(2025, 9, 30)
        )

        internal_amounts = {txn.amount for txn in internal_txns}
        processor_amounts = {txn.amount for txn in processor_txns}

        assert internal_amounts.issubset(processor_amounts)
        assert len(internal_txns) >= 1

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_internal_data_handles_api_error(
        self, mock_get, fetcher, mock_products_response
    ):
        processor_mock = Mock()
        processor_mock.json.return_value = mock_products_response
        processor_mock.raise_for_status = Mock()
        mock_get.return_value = processor_mock
        processor_txns = fetcher.fetch_processor_data(run_date=date(2025, 9, 30))

        mock_get.side_effect = requests.RequestException("Internal API Error")
        with pytest.raises(requests.RequestException):
            fetcher.fetch_internal_data(processor_txns=processor_txns)

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_merchant_id_logic(
        self, mock_get, fetcher, mock_products_response
    ):
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
        session_mock = Mock()
        fetcher.session = session_mock
        fetcher.close()
        session_mock.close.assert_called_once()

    @patch("src.data_fetcher.requests.Session.get")
    def test_fetch_processor_data_with_pagination_and_logging(
        self, mock_get, fetcher, caplog
    ):
        page1 = {"products": [{"id": i, "price": 100.0} for i in range(30)]}
        page2 = {"products": [{"id": i + 30, "price": 200.0} for i in range(20)]}
        page3 = {"products": []}

        mock_responses = []
        for response_data in [page1, page2, page3]:
            mock_resp = Mock()
            mock_resp.json.return_value = response_data
            mock_resp.raise_for_status = Mock()
            mock_responses.append(mock_resp)

        mock_get.side_effect = mock_responses
        caplog.set_level(logging.DEBUG)

        transactions = fetcher.fetch_processor_data()

        assert len(transactions) == 50

        fetch_logs = [
            record for record in caplog.records if "Fetching page" in record.message
        ]
        assert len(fetch_logs) >= 2


def test_make_request_with_retry_timeout(monkeypatch):
    """Ensure retry logic handles timeouts correctly."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")

    mock_get = MagicMock(side_effect=requests.Timeout("timeout"))
    monkeypatch.setattr(fetcher.session, "get", mock_get)

    with pytest.raises(requests.Timeout):
        fetcher._make_request_with_retry("http://mock-api/products")

    # Should have retried max_retries times
    assert mock_get.call_count == fetcher.max_retries


def test_fetch_processor_data_stops_on_empty(monkeypatch):
    """Verify pagination stops when API returns empty product list."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")

    # Mock _make_request_with_retry to return an empty product list
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"products": []}
    monkeypatch.setattr(fetcher, "_make_request_with_retry", lambda url: mock_response)

    result = fetcher.fetch_processor_data()
    assert result == []  # No transactions fetched


def test_fetch_internal_data_handles_timeout(monkeypatch):
    """Ensure internal data fetching handles timeouts gracefully."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")

    # Simulate timeout on _make_request_with_retry
    monkeypatch.setattr(
        fetcher,
        "_make_request_with_retry",
        lambda url: (_ for _ in ()).throw(requests.Timeout()),
    )

    with pytest.raises(requests.Timeout):
        fetcher.fetch_internal_data(processor_txns=[])


def test_pagination_timeout(monkeypatch, caplog):
    """Test pagination timeout after max_duration."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")
    
    # Mock time.time to simulate timeout
    call_count = [0]
    def mock_time():
        call_count[0] += 1
        if call_count[0] == 1:
            return 1000  # Start time
        elif call_count[0] == 2:
            return 1000  # Still within timeout for first iteration
        else:
            return 1301  # Timeout on subsequent calls
    
    monkeypatch.setattr("src.data_fetcher.time.time", mock_time)
    
    # Mock response that returns products to trigger pagination
    mock_response = Mock()
    mock_response.json.return_value = {"products": [{"id": 1, "price": 100.0}]}
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr(fetcher, "_make_request_with_retry", lambda url: mock_response)
    
    with caplog.at_level(logging.ERROR):
        result = fetcher.fetch_processor_data()
    
    # Should have timeout error in logs
    assert any("Pagination timeout" in record.message for record in caplog.records)
    # Timeout happens before processing any products, so result is empty
    assert len(result) == 0


def test_fetch_processor_data_http_error(monkeypatch):
    """Test HTTP error handling in fetch_processor_data."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")
    
    def mock_request(url):
        raise requests.HTTPError("404 Not Found")
    
    monkeypatch.setattr(fetcher, "_make_request_with_retry", mock_request)
    
    with pytest.raises(requests.HTTPError):
        fetcher.fetch_processor_data()


def test_fetch_processor_data_unexpected_error(monkeypatch):
    """Test unexpected error handling in fetch_processor_data."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")
    
    def mock_request(url):
        raise ValueError("Unexpected error")
    
    monkeypatch.setattr(fetcher, "_make_request_with_retry", mock_request)
    
    with pytest.raises(ValueError):
        fetcher.fetch_processor_data()


def test_fetch_internal_data_unexpected_error(monkeypatch):
    """Test unexpected error handling in fetch_internal_data."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")
    
    def mock_request(url):
        raise ValueError("Unexpected internal error")
    
    monkeypatch.setattr(fetcher, "_make_request_with_retry", mock_request)
    
    with pytest.raises(ValueError):
        fetcher.fetch_internal_data(processor_txns=[])


def test_context_manager():
    """Test context manager functionality."""
    with DataFetcher("http://mock-api", "http://mock-internal", "test") as fetcher:
        assert isinstance(fetcher, DataFetcher)
        assert hasattr(fetcher, 'session')
    # Session should be closed after exiting context


def test_close_session_error(monkeypatch):
    """Test error handling in close method."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")
    
    # Mock session.close to raise an exception
    def mock_close():
        raise Exception("Close error")
    
    fetcher.session.close = mock_close
    
    # Should not raise exception, just log warning
    fetcher.close()


def test_make_request_unknown_failure():
    """Test unknown failure path in _make_request_with_retry."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")
    
    # Mock to simulate no exception but also no successful response
    original_get = fetcher.session.get
    
    def mock_get(*args, **kwargs):
        # Don't raise exception, but also don't return response
        # This should trigger the final raise at the end
        pass
    
    fetcher.session.get = mock_get
    fetcher.max_retries = 0  # No retries to speed up test
    
    with pytest.raises(requests.RequestException, match="Request failed for unknown reason"):
        fetcher._make_request_with_retry("http://test")


def test_fetch_processor_data_invalid_product_data(monkeypatch, caplog):
    """Test handling of invalid product data that causes exceptions."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")
    
    # Mock response with invalid product data that will cause KeyError
    mock_response = Mock()
    mock_response.json.return_value = {
        "products": [
            {},  # Missing required fields - will cause KeyError
        ]
    }
    mock_response.raise_for_status = Mock()
    
    # Mock to return empty products on subsequent calls to stop pagination
    call_count = [0]
    def mock_request(url):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_response
        # Return empty products to stop pagination
        empty_response = Mock()
        empty_response.json.return_value = {"products": []}
        empty_response.raise_for_status = Mock()
        return empty_response
    
    monkeypatch.setattr(fetcher, "_make_request_with_retry", mock_request)
    
    with caplog.at_level(logging.WARNING):
        result = fetcher.fetch_processor_data()
    
    # Should skip invalid records and log warnings
    assert len(result) == 0  # No valid products processed
    assert any("Skipping invalid processor record" in record.message for record in caplog.records)


def test_fetch_internal_data_invalid_transaction_data(monkeypatch, caplog):
    """Test handling of invalid transaction data in fetch_internal_data."""
    from datetime import datetime
    
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")
    
    # Create processor transactions with one invalid transaction
    valid_txn = Transaction(
        transaction_id="TXN_TEST_001",
        processor_name="test",
        amount=Decimal("100.00"),
        currency="USD",
        status="completed",
        merchant_id="MERCH_001",
        transaction_date=datetime.utcnow(),
        reference_number="REF_001",
        fee=Decimal("3.20")
    )
    
    # Mock the processor transaction to have invalid amount
    invalid_txn = Mock()
    invalid_txn.amount = "invalid_amount"  # This will cause TypeError
    invalid_txn.transaction_id = "TXN_INVALID"
    invalid_txn.merchant_id = "MERCH_INVALID"
    invalid_txn.transaction_date = datetime.utcnow()
    invalid_txn.reference_number = "REF_INVALID"
    
    processor_txns = [valid_txn, invalid_txn]
    
    # Mock successful API call
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr(fetcher, "_make_request_with_retry", lambda url: mock_response)
    
    # Mock random to ensure we try to process the invalid transaction
    monkeypatch.setattr("src.data_fetcher.random.uniform", lambda a, b: 1.0)  # 100% capture rate
    monkeypatch.setattr("src.data_fetcher.random.sample", lambda lst, k: list(range(len(lst))))
    
    with caplog.at_level(logging.WARNING):
        result = fetcher.fetch_internal_data(processor_txns=processor_txns)
    
    # Should skip invalid transaction and log warning
    assert len(result) == 1  # Only valid transaction processed
    assert any("Skipping invalid internal record" in record.message for record in caplog.records)


def test_close_session_without_session():
    """Test close method when session doesn't exist."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")
    # Remove session attribute
    delattr(fetcher, 'session')
    
    # Should not raise exception
    fetcher.close()


def test_environment_variable_page_size(monkeypatch):
    """Test PROCESSOR_API_PAGE_SIZE environment variable usage."""
    fetcher = DataFetcher("http://mock-api", "http://mock-internal", "test")
    
    # Set environment variable
    monkeypatch.setenv("PROCESSOR_API_PAGE_SIZE", "25")
    
    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = {"products": []}
    mock_response.raise_for_status = Mock()
    
    # Track the URL to verify page size is used
    called_urls = []
    def mock_request(url):
        called_urls.append(url)
        return mock_response
    
    monkeypatch.setattr(fetcher, "_make_request_with_retry", mock_request)
    
    result = fetcher.fetch_processor_data()
    
    # Verify the environment variable was used in the URL
    assert len(called_urls) == 1
    assert "limit=25" in called_urls[0]
    assert len(result) == 0
