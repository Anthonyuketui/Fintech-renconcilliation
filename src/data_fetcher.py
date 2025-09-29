"""
Fetches and normalizes transaction data from external sources.

The DataFetcher acts as a translator, encapsulating all external API interactions.
It converts the mock API's raw data (products, posts) into a standardized,
validated Transaction model using Pydantic, ensuring all financial data uses
the precise Decimal type for accuracy (99.9% requirement).
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from typing import List, Optional
from decimal import Decimal

import requests
from pydantic import ValidationError

logger = logging.getLogger(__name__)

from models import Transaction


class DataFetcher:
    """
    Fetches transaction data from a payment processor and internal API.
    Uses Dependency Injection for configuration and robust error handling.
    """

    def __init__(self, processor_api_base_url: str, internal_api_base_url: str, processor_name: str) -> None:
        self.processor_api_base_url = processor_api_base_url.rstrip("/")
        self.internal_api_base_url = internal_api_base_url.rstrip("/")
        self.processor_name = processor_name.lower()
        
        # Use a requests.Session for persistent connections
        self.session = requests.Session()

    def fetch_processor_data(self, run_date: Optional[date] = None) -> List[Transaction]:
        """
        Retrieve and normalize transactions from the payment processor (mock: products API).
        Returns a list of validated Transaction objects.
        """
        if run_date is None:
            run_date = date.today()

        url = f"{self.processor_api_base_url}/products"
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Failed to fetch processor data from %s: %s", url, exc)
            raise

        data = resp.json()
        products = data.get("products") or data
        transactions: List[Transaction] = []

        # Limit to 30 for demo purposes
        for idx, item in enumerate(products[:30]):
            try:
                # Financial Precision: Convert to Decimal
                raw_price = str(item.get("price", 0.0))
                amount_decimal = Decimal(raw_price)
                fee_decimal = amount_decimal * Decimal('0.029') + Decimal('0.30')  # Realistic Stripe fees

                # Unique ID Creation
                trans_id = f"TXN_{self.processor_name.upper()}_{run_date.strftime('%Y%m%d')}_{int(item.get('id', 0)):04d}"
                
                transaction = Transaction(
                    transaction_id=trans_id,
                    processor_name=self.processor_name,
                    amount=amount_decimal, 
                    currency="USD",
                    status="completed",
                    merchant_id=str(item.get("brand") or item.get("category") or "UNKNOWN").upper(),
                    transaction_date=datetime.utcnow(),
                    reference_number=f"REF_{self.processor_name.upper()}_{item.get('id')}",
                    fee=fee_decimal,
                )
                transactions.append(transaction)
                
            except (TypeError, ValidationError) as exc:
                logger.warning("Skipping invalid processor item due to validation error: %s", exc)
                continue
            
        logger.info("Successfully fetched and normalized %d transactions from processor %s", 
                   len(transactions), self.processor_name.upper())
        return transactions

    def fetch_internal_data(self, run_date: Optional[date] = None) -> List[Transaction]:
        """
        Retrieve and normalize internal transactions (mock: posts API).
        
        FIXED: Creates transactions with same processor_name to enable proper reconciliation.
        Intentionally creates some missing transactions to demonstrate discrepancies.
        """
        if run_date is None:
            run_date = date.today()

        url = f"{self.internal_api_base_url}/posts"
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Failed to fetch internal data from %s: %s", url, exc)
            raise

        posts = resp.json()
        if not isinstance(posts, list):
            posts = posts.get("data", [])
            
        transactions: List[Transaction] = []

        # Create transactions that will partially match processor data
        # Use only first 25 posts to create discrepancies (since processor has 30)
        for idx, post in enumerate(posts[:25]):
            try:
                # Use same ID format as processor for matching transactions
                trans_id = f"TXN_{self.processor_name.upper()}_{run_date.strftime('%Y%m%d')}_{int(post.get('id')):04d}"
                
                # Use post ID as a basis for amount (different from processor)
                amount_decimal = Decimal(str(post.get('id', 1))) * Decimal('2.50')
                
                transaction = Transaction(
                    transaction_id=trans_id,
                    processor_name=self.processor_name,  # FIXED: Use same processor name
                    amount=amount_decimal,
                    currency="USD",
                    status="completed",
                    merchant_id=f"MERCH_{post.get('userId', 0):03d}",
                    transaction_date=datetime.utcnow(),
                    reference_number=f"INT_{post.get('id')}",
                    fee=Decimal('0.00'),  # Internal records might not have fees
                )
                transactions.append(transaction)
                
            except (TypeError, ValidationError) as exc:
                logger.warning("Skipping invalid internal item due to validation error: %s", exc)
                continue

        logger.info("Successfully fetched and normalized %d transactions from internal API", len(transactions))
        return transactions

    def close(self):
        """Close the requests session."""
        self.session.close()