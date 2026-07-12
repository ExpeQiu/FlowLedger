from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from models import (
    AccountType,
    BillFrequency,
    CategoryType,
    HoldingType,
    ImportStatus,
    LiabilityType,
    TxSource,
    TxType,
)


class AccountCreate(BaseModel):
    name: str
    type: AccountType
    balance: Decimal = Decimal("0")
    currency: str = "CNY"


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[AccountType] = None
    balance: Optional[Decimal] = None
    currency: Optional[str] = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    type: AccountType
    balance: Decimal
    currency: str
    created_at: datetime


class CategoryCreate(BaseModel):
    name: str
    type: CategoryType
    parent_id: Optional[UUID] = None
    color: Optional[str] = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    type: CategoryType
    parent_id: Optional[UUID]
    color: Optional[str]


class TransactionCreate(BaseModel):
    type: TxType
    amount: Decimal = Field(gt=0)
    date: date
    account_id: UUID
    category_id: Optional[UUID] = None
    merchant: Optional[str] = None
    note: Optional[str] = None
    source: TxSource = TxSource.manual
    to_account_id: Optional[UUID] = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: TxType
    amount: Decimal
    date: date
    account_id: UUID
    category_id: Optional[UUID]
    merchant: Optional[str]
    note: Optional[str]
    source: TxSource
    transfer_pair_id: Optional[UUID]
    created_at: datetime
    account_name: Optional[str] = None
    category_name: Optional[str] = None


class BudgetCreate(BaseModel):
    category_id: UUID
    period: str
    amount: Decimal = Field(gt=0)
    alert_threshold: int = 80


class BudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    period: str
    amount: Decimal
    alert_threshold: int
    category_name: Optional[str] = None
    spent: Optional[Decimal] = None
    usage_pct: Optional[float] = None


class HoldingCreate(BaseModel):
    symbol: str
    name: str
    type: HoldingType
    quantity: Decimal
    cost_price: Decimal
    current_price: Decimal
    account_id: UUID
    target_pct: Optional[Decimal] = None


class HoldingUpdate(BaseModel):
    quantity: Optional[Decimal] = None
    cost_price: Optional[Decimal] = None
    current_price: Optional[Decimal] = None
    target_pct: Optional[Decimal] = None


class HoldingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    symbol: str
    name: str
    type: HoldingType
    quantity: Decimal
    cost_price: Decimal
    current_price: Decimal
    account_id: UUID
    target_pct: Optional[Decimal]
    market_value: Optional[Decimal] = None
    profit_pct: Optional[float] = None


class LiabilityCreate(BaseModel):
    name: str
    type: LiabilityType
    principal: Decimal
    interest_rate: Optional[Decimal] = None
    due_date: Optional[date] = None
    min_payment: Optional[Decimal] = None
    note: Optional[str] = None


class LiabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    type: LiabilityType
    principal: Decimal
    interest_rate: Optional[Decimal]
    due_date: Optional[date]
    min_payment: Optional[Decimal]
    note: Optional[str]


class RecurringBillCreate(BaseModel):
    name: str
    amount: Decimal
    frequency: BillFrequency
    next_due: date
    category_id: Optional[UUID] = None
    account_id: Optional[UUID] = None
    auto_create: bool = False
    note: Optional[str] = None


class RecurringBillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    amount: Decimal
    frequency: BillFrequency
    next_due: date
    category_id: Optional[UUID]
    account_id: Optional[UUID]
    auto_create: bool
    note: Optional[str]


class RuleCreate(BaseModel):
    pattern: str
    category_id: UUID
    priority: int = 0


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pattern: str
    category_id: UUID
    priority: int
    is_active: bool
    category_name: Optional[str] = None


class GoalCreate(BaseModel):
    name: str
    target_amount: Decimal
    current_amount: Decimal = Decimal("0")
    deadline: Optional[date] = None
    note: Optional[str] = None


class GoalUpdate(BaseModel):
    current_amount: Optional[Decimal] = None
    target_amount: Optional[Decimal] = None
    deadline: Optional[date] = None
    note: Optional[str] = None


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    target_amount: Decimal
    current_amount: Decimal
    deadline: Optional[date]
    note: Optional[str]
    progress_pct: Optional[float] = None


class TrendItem(BaseModel):
    month: str
    income: Decimal
    expense: Decimal


class BudgetCategoryItem(BaseModel):
    category: str
    spent: Decimal
    budget: Decimal
    usage_pct: float
    color: Optional[str] = None


class AssetItem(BaseModel):
    name: str
    value: Decimal
    pct: float


class AlertItem(BaseModel):
    date: str
    title: str
    detail: str


class DashboardOut(BaseModel):
    net_worth: Decimal
    monthly_expense: Decimal
    budget_usage_pct: float
    investment_return: Decimal
    cash_flow: Decimal
    trends: list[TrendItem]
    budget_by_category: list[BudgetCategoryItem]
    asset_distribution: list[AssetItem]
    alerts: list[AlertItem]


class ImportPreviewRow(BaseModel):
    date: date
    amount: Decimal
    merchant: Optional[str]
    note: Optional[str]
    category_name: Optional[str]
    is_duplicate: bool = False


class ImportPreviewOut(BaseModel):
    rows: list[ImportPreviewRow]
    total: int
    duplicates: int


class ImportResultOut(BaseModel):
    job_id: UUID
    imported: int
    skipped: int
    status: ImportStatus


class PortfolioSummary(BaseModel):
    total_value: Decimal
    total_cost: Decimal
    profit: Decimal
    profit_pct: float
    annualized_return: float
    max_concentration: float
    holdings: list[HoldingOut]
    rebalance: list[dict]


class CashFlowForecast(BaseModel):
    days: int
    starting_balance: Decimal
    ending_balance: Decimal
    items: list[dict]


class MonthlyReport(BaseModel):
    month: str
    total_income: Decimal
    total_expense: Decimal
    net: Decimal
    by_category: list[dict]
    vs_last_month: Optional[dict] = None
