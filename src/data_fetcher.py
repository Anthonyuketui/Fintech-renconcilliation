from __future__ import annotations

import logging
import random
import time
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
import requests
from pydantic import ValidationError
from models import Transaction

logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Retrieves transaction data from payment processor APIs and internal systems.

    For this demo, public APIs (dummyjson, jsonplaceholder) are used and transformed
    into realistic transaction records. In production, this would connect directly
    to Stripe, Square, or PayPal APIs.
    """

    def __init__(
        self,
        processor_api_base_url: str,
        internal_api_base_url: str,
        processor_name: str,
        max_retries: int = 3,
    ) -> None:
        """Initialize DataFetcher with API endpoints, processor name, and retry policy."""
        self.processor_api_base_url = processor_api_base_url.rstrip("/")
        self.internal_api_base_url = internal_api_base_url.rstrip("/")
        self.processor_name = processor_name.lower()
        self.max_retries = max_retries
        self.session = requests.Session()

    def _make_request_with_retry(
        self, url: str, timeout: int = 30
    ) -> requests.Response:
        """
        Perform HTTP GET requests with exponential backoff retry logic.

        Network interruptions are common; retries improve reliability without
        overwhelming failing services.
        """
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()
                return response

            except requests.Timeout as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Request timeout (attempt {attempt + 1}/{self.max_retries}). "
                        f"Retrying in {wait_time}s... URL: {url}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {self.max_retries} attempts failed for: {url}")
                    raise

            except requests.RequestException as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Request error (attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Request failed after {self.max_retries} attempts: {e}"
                    )
                    raise

        # Fallback in case no response was returned
        if last_exception:
            raise last_exception
        raise requests.RequestException("Request failed for unknown reason")

    def fetch_processor_data(
        self, run_date: Optional[date] = None
    ) -> List[Transaction]:
        """
        Fetch transactions from the payment processor.

        For this demo, dummy product data is converted to transactions. In production,
        this would query actual processor endpoints and paginate through all transactions.
        """
        if run_date is None:
            run_date = date.today()

        transactions: List[Transaction] = []

        try:
            url = f"{self.processor_api_base_url}/products"
            response = self._make_request_with_retry(url)
            data = response.json()

            products = data.get("products", [])[:30]  # Limit to 30 for demo

            for idx, product in enumerate(products, 1):
                try:
                    amount_decimal = Decimal(str(product["price"])).quantize(
                        Decimal("0.01")
                    )
                    fee_decimal = (
                        amount_decimal * Decimal("0.029") + Decimal("0.30")
                    ).quantize(Decimal("0.01"))

                    trans_id = f"TXN_{self.processor_name.upper()}_{run_date.strftime('%Y%m%d')}_{idx:04d}"

                    transaction = Transaction(
                        transaction_id=trans_id,
                        processor_name=self.processor_name,
                        amount=amount_decimal,
                        currency="USD",
                        status="completed",
                        merchant_id=f"MERCH_{product['id']:03d}",
                        transaction_date=datetime.utcnow(),
                        reference_number=f"REF_{self.processor_name.upper()}_{idx}",
                        fee=fee_decimal,
                    )
                    transactions.append(transaction)

                except (TypeError, ValidationError, KeyError) as exc:
                    # Skip malformed records
                    logger.warning(f"Skipping invalid processor record: {exc}")
                    continue

        except requests.Timeout:
            logger.error(f"Processor API timed out: {self.processor_api_base_url}")
            raise
        except requests.RequestException as e:
            logger.error(f"Failed to fetch processor data: {e}")
            raise

        logger.info(
            f"Fetched {len(transactions)} transactions from {self.processor_name.upper()}"
        )
        return transactions

    def fetch_internal_data(
        self,
        processor_txns: Optional[List[Transaction]] = None,
        run_date: Optional[date] = None,
    ) -> List[Transaction]:
        """
        Fetch internal transaction records.

        Simulates missing transactions (80-95% capture rate) to mimic real-world
        reconciliation scenarios where some transactions fail to be captured internally.
        """
        if run_date is None:
            run_date = date.today()

        if processor_txns is None:
            processor_txns = self.fetch_processor_data(run_date=run_date)

        transactions: List[Transaction] = []

        try:
            url = f"{self.internal_api_base_url}/posts"
            self._make_request_with_retry(url)

            capture_rate = random.uniform(0.80, 0.95)
            num_to_capture = int(len(processor_txns) * capture_rate)
            captured_indices = sorted(
                random.sample(range(len(processor_txns)), num_to_capture)
            )

            logger.info(
                f"Simulating {capture_rate:.1%} internal capture rate "
                f"({num_to_capture}/{len(processor_txns)} transactions)"
            )

            for proc_idx in captured_indices:
                processor_txn = processor_txns[proc_idx]

                try:
                    amount_decimal = processor_txn.amount
                    fee_decimal = (
                        amount_decimal * Decimal("0.02") + Decimal("0.30")
                    ).quantize(Decimal("0.01"))

                    transaction = Transaction(
                        transaction_id=processor_txn.transaction_id,
                        processor_name=self.processor_name,
                        amount=amount_decimal,
                        currency="USD",
                        status="completed",
                        merchant_id=processor_txn.merchant_id,
                        transaction_date=processor_txn.transaction_date,
                        reference_number=f"INT_{proc_idx+1:04d}",
                        fee=fee_decimal,
                    )
                    transactions.append(transaction)

                except (TypeError, ValidationError, KeyError) as exc:
                    logger.warning(f"Skipping invalid internal record: {exc}")
                    continue

        except requests.Timeout:
            logger.error(f"Internal API timed out: {self.internal_api_base_url}")
            raise
        except requests.RequestException as e:
            logger.error(f"Failed to fetch internal data: {e}")
            raise

        logger.info(f"Fetched {len(transactions)} transactions from internal API")
        return transactions

    def close(self):
        """
        Close the requests session to release connection pools.

        Important for long-running services to avoid resource leaks.
        """
        self.session.close()
