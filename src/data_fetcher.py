from __future__ import annotations

import logging
import random
import time
from datetime import datetime, date
from typing import List, Optional
from decimal import Decimal

import requests
from pydantic import ValidationError

from models import Transaction

logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Handles data retrieval from payment processor APIs and internal systems.
    
    Since we're working with public APIs (dummyjson, jsonplaceholder) for this demo,
    we transform their responses into realistic transaction records. In production,
    this would connect directly to Stripe/Square/PayPal APIs.
    """

    def __init__(
        self, 
        processor_api_base_url: str, 
        internal_api_base_url: str, 
        processor_name: str, 
        max_retries: int = 3
    ) -> None:
        self.processor_api_base_url = processor_api_base_url.rstrip("/")
        self.internal_api_base_url = internal_api_base_url.rstrip("/")
        self.processor_name = processor_name.lower()
        self.max_retries = max_retries
        self.session = requests.Session()

    def _make_request_with_retry(self, url: str, timeout: int = 30) -> requests.Response:
        """
        Wraps HTTP requests with exponential backoff retry logic.
        
        Network issues are common in production - APIs go down, connections drop, etc.
        Rather than failing immediately, we retry with increasing delays (1s, 2s, 4s).
        This significantly improves reliability without hammering failing services.
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
                    wait_time = 2 ** attempt
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
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Request error (attempt {attempt + 1}/{self.max_retries}): {str(e)}. "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {self.max_retries} attempts: {str(e)}")
                    raise
        
        # Shouldn't reach here, but handle it anyway
        if last_exception:
            raise last_exception
        raise requests.RequestException("Request failed for unknown reason")

    def fetch_processor_data(self, run_date: Optional[date] = None) -> List[Transaction]:
        """
        Fetches transaction data from the payment processor.
        
        In production, this would hit Stripe's /v1/charges or Square's /v2/payments endpoints.
        For this assessment, we're using dummyjson's product catalog and transforming prices
        into transaction amounts. This simulates receiving a batch of completed payments.
        
        We limit to 30 transactions to keep the demo manageable, but production systems
        would paginate through thousands of daily transactions.
        """
        if run_date is None:
            run_date = date.today()

        transactions: List[Transaction] = []

        try:
            url = f"{self.processor_api_base_url}/products"
            response = self._make_request_with_retry(url)
            data = response.json()
            
            # Cap at 30 to avoid overwhelming the demo
            products = data.get('products', [])[:30]

            for idx, product in enumerate(products, 1):
                try:
                    # Product price becomes our transaction amount
                    amount_decimal = Decimal(str(product['price'])).quantize(Decimal('0.01'))
                    
                    # Standard processor fee: 2.9% + $0.30 (typical for Stripe/Square)
                    fee_decimal = (amount_decimal * Decimal('0.029') + Decimal('0.30')).quantize(Decimal('0.01'))

                    # Generate a unique transaction ID using processor name, date, and sequence
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
                    # Skip malformed records rather than crashing the entire batch
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
        run_date: Optional[date] = None
    ) -> List[Transaction]:
        """
        Fetches transaction records from our internal database/API.
        
        Here's the key insight: in real reconciliation scenarios, your internal system
        might miss some transactions due to webhook failures, API timeouts, or sync delays.
        This method simulates that by randomly selecting 80-95% of processor transactions
        to appear in our internal records.
        
        The reconciliation engine will then identify which transactions the processor
        recorded but we somehow missed internally. This is the core business value -
        finding money we're owed but haven't tracked.
        """
        if run_date is None:
            run_date = date.today()

        # Fetch processor data if not provided (allows standalone testing)
        if processor_txns is None:
            processor_txns = self.fetch_processor_data(run_date=run_date)

        transactions: List[Transaction] = []

        try:
            # In production, this would query our internal transaction database
            # For the demo, we fetch posts from jsonplaceholder (not actually used for content)
            url = f"{self.internal_api_base_url}/posts"
            response = self._make_request_with_retry(url)
            
            # Simulate realistic internal capture rate (some transactions always slip through)
            # Real-world systems typically achieve 95-99% capture, depending on reliability
            capture_rate = random.uniform(0.80, 0.95)
            num_to_capture = int(len(processor_txns) * capture_rate)
            
            # Randomly select which processor transactions made it into our internal system
            # This creates a different reconciliation scenario each time we run
            captured_indices = sorted(random.sample(range(len(processor_txns)), num_to_capture))
            
            logger.info(
                f"Simulating {capture_rate:.1%} internal capture rate "
                f"({num_to_capture}/{len(processor_txns)} transactions)"
            )

            for proc_idx in captured_indices:
                processor_txn = processor_txns[proc_idx]
                
                try:
                    # Internal records should match processor amounts exactly
                    amount_decimal = processor_txn.amount
                    
                    # Our internal fee calculation might differ slightly from processor's
                    fee_decimal = (amount_decimal * Decimal('0.02') + Decimal('0.30')).quantize(Decimal('0.01'))

                    # Critical: Use the SAME transaction_id as the processor
                    # This is how reconciliation matches records between systems
                    # In production, this ID would come from the webhook payload or API response
                    transaction = Transaction(
                        transaction_id=processor_txn.transaction_id,  # Must match!
                        processor_name=self.processor_name,
                        amount=amount_decimal,
                        currency="USD",
                        status="completed",
                        merchant_id=processor_txn.merchant_id,
                        transaction_date=processor_txn.transaction_date,
                        reference_number=f"INT_{proc_idx+1:04d}",  # Internal reference differs
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
        Clean up the requests session.
        
        Sessions maintain connection pools, so it's good practice to close them
        when done. This is especially important for long-running services.
        """
        self.session.close()