from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .contracts import InputCase


CENT = Decimal("0.01")


def money(value: Decimal | str | int) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_csv_datetime(value: str) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class OrderRow:
    order_id: str
    status: str
    carrier_date: datetime | None
    customer_date: datetime | None
    estimated_date: datetime


@dataclass(frozen=True)
class ItemRow:
    order_id: str
    item_id: int
    seller_id: str
    shipping_limit_date: datetime
    price: Decimal
    freight: Decimal

    @property
    def entity_id(self) -> str:
        return f"{self.order_id}:{self.item_id}"


@dataclass(frozen=True)
class PaymentRow:
    order_id: str
    sequential: int
    value: Decimal

    @property
    def entity_id(self) -> str:
        return f"{self.order_id}:{self.sequential}"


@dataclass(frozen=True)
class CaseContext:
    case: InputCase
    order: OrderRow
    items: tuple[ItemRow, ...]
    payments: tuple[PaymentRow, ...]
    known_seller_ids: frozenset[str]

    @property
    def item_total(self) -> Decimal:
        return money(sum((row.price for row in self.items), Decimal("0")))

    @property
    def freight_total(self) -> Decimal:
        return money(sum((row.freight for row in self.items), Decimal("0")))

    @property
    def payment_total(self) -> Decimal:
        return money(sum((row.value for row in self.payments), Decimal("0")))

    @property
    def payment_difference(self) -> Decimal:
        return money(abs(self.payment_total - self.item_total - self.freight_total))

    @property
    def seller_ids(self) -> tuple[str, ...]:
        return tuple(sorted({row.seller_id for row in self.items}))

    @property
    def late_seller_ids(self) -> tuple[str, ...]:
        carrier_date = self.order.carrier_date
        if carrier_date is None:
            return ()
        return tuple(
            sorted(
                {
                    row.seller_id
                    for row in self.items
                    if carrier_date > row.shipping_limit_date
                }
            )
        )

    @property
    def delivered_after_estimate(self) -> bool:
        return bool(
            self.order.customer_date
            and self.order.customer_date > self.order.estimated_date
        )

    @property
    def delivered_within_estimate(self) -> bool:
        return bool(
            self.order.customer_date
            and self.order.customer_date <= self.order.estimated_date
        )


class DataRepository:
    """Read the Olist snapshot once and expose immutable per-order contexts."""

    def __init__(
        self,
        orders: dict[str, OrderRow],
        items: dict[str, tuple[ItemRow, ...]],
        payments: dict[str, tuple[PaymentRow, ...]],
        seller_ids: frozenset[str],
    ) -> None:
        self._orders = orders
        self._items = items
        self._payments = payments
        self._seller_ids = seller_ids

    @classmethod
    def load(cls, data_dir: Path, target_order_ids: set[str]) -> "DataRepository":
        orders: dict[str, OrderRow] = {}
        with (data_dir / "olist_orders_dataset.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                order_id = row["order_id"]
                if order_id not in target_order_ids:
                    continue
                estimated = parse_csv_datetime(row["order_estimated_delivery_date"])
                if estimated is None:
                    raise ValueError(f"Order {order_id} has no estimated delivery date")
                orders[order_id] = OrderRow(
                    order_id=order_id,
                    status=row["order_status"],
                    carrier_date=parse_csv_datetime(row["order_delivered_carrier_date"]),
                    customer_date=parse_csv_datetime(row["order_delivered_customer_date"]),
                    estimated_date=estimated,
                )

        item_lists: dict[str, list[ItemRow]] = {}
        with (data_dir / "olist_order_items_dataset.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                order_id = row["order_id"]
                if order_id not in target_order_ids:
                    continue
                item_lists.setdefault(order_id, []).append(
                    ItemRow(
                        order_id=order_id,
                        item_id=int(row["order_item_id"]),
                        seller_id=row["seller_id"],
                        shipping_limit_date=datetime.fromisoformat(row["shipping_limit_date"]),
                        price=money(row["price"]),
                        freight=money(row["freight_value"]),
                    )
                )

        payment_lists: dict[str, list[PaymentRow]] = {}
        with (data_dir / "olist_order_payments_dataset.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                order_id = row["order_id"]
                if order_id not in target_order_ids:
                    continue
                payment_lists.setdefault(order_id, []).append(
                    PaymentRow(
                        order_id=order_id,
                        sequential=int(row["payment_sequential"]),
                        value=money(row["payment_value"]),
                    )
                )

        seller_ids: set[str] = set()
        with (data_dir / "olist_sellers_dataset.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                seller_ids.add(row["seller_id"])

        missing = target_order_ids - orders.keys()
        if missing:
            raise KeyError(f"Unknown order IDs: {sorted(missing)}")

        items = {
            order_id: tuple(sorted(rows, key=lambda row: row.item_id))
            for order_id, rows in item_lists.items()
        }
        payments = {
            order_id: tuple(sorted(rows, key=lambda row: row.sequential))
            for order_id, rows in payment_lists.items()
        }
        return cls(orders, items, payments, frozenset(seller_ids))

    def context_for(self, case: InputCase) -> CaseContext:
        order_id = case.customer_request.claimed_order_id
        return CaseContext(
            case=case,
            order=self._orders[order_id],
            items=self._items.get(order_id, ()),
            payments=self._payments.get(order_id, ()),
            known_seller_ids=self._seller_ids,
        )

