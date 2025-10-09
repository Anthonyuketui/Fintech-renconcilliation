from __future__ import annotations

import logging
import os
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
    Retrieves transaction data from payment processors and internal systems.
    Uses public APIs for demo; production would connect to actual payment APIs.
    """

    def __init__(
        self,
        processor_api_base_url: str,
        internal_api_base_url: str,
        processor_name: str,
        max_retries: int = 3,
    ) -> None:
        self.processor_api_base_url = processor_api_base_url.rstrip("/")
        self.internal_api_base_url = internal_api_base_url.rstrip("/")
        self.processor_name = processor_name.lower()
        self.max_retries = max_retries
        self.session = requests.Session()

    def _make_request_with_retry(
        self, url: str, timeout: int = 30
    ) -> requests.Response:
        """
        HTTP request with exponential backoff retry logic.
        Improves reliability for network failures and API timeouts.
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
                        f"Request error (attempt {attempt + 1}/{self.max_retries}): {str(e)}. "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Request failed after {self.max_retries} attempts: {str(e)}"
                    )
                    raise

        if last_exception:
            raise last_exception
        raise requests.RequestException("Request failed for unknown reason")

    def fetch_processor_data(
        self, run_date: Optional[date] = None
    ) -> List[Transaction]:
        """
        Fetch transaction data from payment processor.
        Uses pagination with safety limits to prevent infinite loops.
        """
        if run_date is None:
            run_date = date.today()

        page_size = int(os.getenv("PROCESSOR_API_PAGE_SIZE", 50))
        transactions: List[Transaction] = []
        page = 1
        max_pages = 100  # Pagination safety limit
        start_time = time.time()
        max_duration = 300  # Pagination timeout in seconds

        while page <= max_pages:
            if time.time() - start_time > max_duration:
                logger.error(
                    f"Pagination timeout after {max_duration}s, stopping at page {page}"
                )
                break
            
            url = f"{self.processor_api_base_url}/products?page={page}&limit={page_size}"
            logger.info(f"Fetching page {page} with page size {page_size}")

            try:
                response = self._make_request_with_retry(url)
                data = response.json()

                products = data.get("products", [])
                logger.info(f"Fetched {len(products)} products on page {page}")

                if not products:
                    logger.info("No more products to fetch; ending pagination.")
                    break

                for idx, product in enumerate(products, 1):
                    try:
                        amount_decimal = Decimal(str(product["price"])).quantize(
                            Decimal("0.01")
                        )
                        fee_decimal = (
                            amount_decimal * Decimal("0.029") + Decimal("0.30")
                        ).quantize(Decimal("0.01"))

                        page_offset = (page - 1) * page_size
                        trans_id = f"TXN_{self.processor_name.upper()}_{run_date.strftime('%Y%m%d')}_{page_offset + idx:04d}"

                        transaction = Transaction(
                            transaction_id=trans_id,
                            processor_name=self.processor_name,
                            amount=amount_decimal,
                            currency="USD",
                            status="completed",
                            merchant_id=f"MERCH_{product['id']:03d}",
                            transaction_date=datetime.utcnow(),
                            reference_number=f"REF_{self.processor_name.upper()}_{page_offset + idx}",
                            fee=fee_decimal,
                        )
                        transactions.append(transaction)

                    except (TypeError, ValidationError, KeyError) as exc:
                        logger.warning(f"Skipping invalid processor record: {exc}")
                        continue

                page += 1

            except requests.HTTPError as e:
                logger.error(f"HTTP error when fetching processor data: {e}")
                raise
            except requests.RequestException as e:
                logger.error(f"Request exception when fetching processor data: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error when fetching processor data: {e}")
                raise

        logger.info(
            f"Fetched total {len(transactions)} transactions from {self.processor_name.upper()}"
        )
        return transactions

    def fetch_internal_data(
        self,
        processor_txns: Optional[List[Transaction]] = None,
        run_date: Optional[date] = None,
    ) -> List[Transaction]:
        """
        Fetch internal transaction records.
        Simulates realistic capture rate (80-95%) to create reconciliation scenarios.
        """
        if run_date is None:
            run_date = date.today()

        if processor_txns is None:
            processor_txns = self.fetch_processor_data(run_date=run_date)

        transactions: List[Transaction] = []

        try:
            url = f"{self.internal_api_base_url}/posts"
            self._make_request_with_retry(url)

            # Simulate realistic internal capture rate (80-95%)
            capture_rate = random.uniform(0.80, 0.95)  # nosec B311
            num_to_capture = int(len(processor_txns) * capture_rate)

            captured_indices = sorted(
                random.sample(range(len(processor_txns)), num_to_capture)  # nosec B311
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
                        reference_number=f"INT_{processor_txn.reference_number}",
                        fee=fee_decimal,
                    )
                    transactions.append(transaction)

                except (TypeError, ValidationError, KeyError) as exc:
                    logger.warning(f"Skipping invalid internal record: {exc}")
                    continue

        except requests.Timeout as e:
            logger.error(f"Timeout when fetching internal data: {e}")
            raise
        except requests.RequestException as e:
            logger.error(f"Request exception when fetching internal data: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error when fetching internal data: {e}")
            raise

        logger.info(
            f"Fetched {len(transactions)} internal transactions for {self.processor_name.upper()}"
        )
        return transactions

    def __enter__(self) -> 'DataFetcher':
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit with session cleanup."""
        self.close()

    def close(self) -> None:
        """Close the requests session."""
        if hasattr(self, 'session') and self.session:
            try:
                self.session.close()
            except Exception as e:
                logger.warning(f"Error closing session: {e}")