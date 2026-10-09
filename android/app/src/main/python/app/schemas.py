"""
اسکیمای اعتبارسنجی Pydantic — معادل src/server/validation.ts (Zod). عمداً نام فیلدها camelCase
نگه داشته شده (نه snake_case معمول پایتون) چون فرانت‌اند React همین‌الان با همین نام‌ها
(accountId, transactionDate, ...) درخواست POST/PUT می‌فرستد و قرار نیست فرانت‌اند تغییر کند.
"""
from typing import Optional, Literal
from pydantic import BaseModel


class AccountIn(BaseModel):
    name: str
    type: Literal["bank", "cash", "wallet", "other"]
    bankName: Optional[str] = None
    accountNumber: Optional[str] = None
    cardNumber: Optional[str] = None
    iban: Optional[str] = None
    initialBalance: int = 0
    currency: Literal["IRR", "IRT"] = "IRR"
    notes: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[Literal["bank", "cash", "wallet", "other"]] = None
    bankName: Optional[str] = None
    notes: Optional[str] = None
    active: Optional[bool] = None


class TransactionIn(BaseModel):
    accountId: int
    transactionDate: str
    transactionTime: Optional[str] = None
    amount: int
    type: Literal["income", "expense", "adjustment"]
    description: Optional[str] = None
    categoryId: Optional[int] = None
    personId: Optional[int] = None
    notes: Optional[str] = None
    tagIds: Optional[list[int]] = None
    counterparty: Optional[str] = None
    cardNumber: Optional[str] = None
    iban: Optional[str] = None
    bankName: Optional[str] = None
    reason: Optional[str] = None


class TransactionUpdate(BaseModel):
    transactionDate: Optional[str] = None
    amount: Optional[int] = None
    type: Optional[Literal["income", "expense", "adjustment"]] = None
    description: Optional[str] = None
    categoryId: Optional[int] = None
    personId: Optional[int] = None
    notes: Optional[str] = None
    tagIds: Optional[list[int]] = None
    counterparty: Optional[str] = None
    cardNumber: Optional[str] = None
    iban: Optional[str] = None
    bankName: Optional[str] = None
    reason: Optional[str] = None
    excludedFromAnalysis: Optional[bool] = None
    rawTransactionType: Optional[str] = None


class QuickUpdate(BaseModel):
    categoryId: Optional[int] = None
    personId: Optional[int] = None
    tagIds: Optional[list[int]] = None
    excludedFromAnalysis: Optional[bool] = None


class BulkUpdateIn(BaseModel):
    ids: list[int]
    categoryId: Optional[int] = None
    addTagId: Optional[int] = None


class BulkDeleteIn(BaseModel):
    ids: list[int]


class TransferIn(BaseModel):
    fromAccountId: int
    toAccountId: int
    amount: int
    date: str
    description: Optional[str] = None


class PersonIn(BaseModel):
    name: str
    phone: Optional[str] = None
    description: Optional[str] = None
    accountNumber: Optional[str] = None
    notes: Optional[str] = None


class CategoryIn(BaseModel):
    name: str
    parentId: Optional[int] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class TagIn(BaseModel):
    name: str
    color: Optional[str] = None


class DebtIn(BaseModel):
    kind: Literal["receivable", "payable"]
    personId: int
    originalAmount: int
    createdDate: str
    dueDate: Optional[str] = None
    description: Optional[str] = None


class DebtPaymentIn(BaseModel):
    amount: int
    date: str
    transactionId: Optional[int] = None


class LoanIn(BaseModel):
    name: str
    lender: str
    principal: int
    interestRateBps: Optional[int] = None
    termMonths: int
    installmentAmount: int
    startDate: str
    accountId: Optional[int] = None
    notes: Optional[str] = None


class InstallmentPaymentIn(BaseModel):
    amount: int
    transactionId: Optional[int] = None


class CustomerIn(BaseModel):
    name: str
    phone: Optional[str] = None
    description: Optional[str] = None


class InstallmentSaleIn(BaseModel):
    customerId: int
    date: str
    itemAmount: int
    discount: int = 0
    downPayment: int = 0
    installmentCount: int
    paymentTerms: Optional[str] = None


class SalePaymentIn(BaseModel):
    amount: int
    date: str
    accountId: Optional[int] = None
    transactionId: Optional[int] = None
    notes: Optional[str] = None


class RuleIn(BaseModel):
    name: str
    condition: dict
    actions: dict
    active: bool = True
    autoApply: bool = False


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    condition: Optional[dict] = None
    actions: Optional[dict] = None
    active: Optional[bool] = None
    autoApply: Optional[bool] = None


class BudgetIn(BaseModel):
    categoryId: int
    month: str
    amount: int


class SavedFilterIn(BaseModel):
    name: str
    filters: dict


class AiSearchIn(BaseModel):
    query: str
