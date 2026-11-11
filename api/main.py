from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth_internal import InternalTokenMiddleware, _expected_token
from logging_config import logger
from routes.accounts import router as accounts_router
from routes.budgets import router as budgets_router
from routes.categories import router as categories_router
from routes.dashboard import router as dashboard_router
from routes.goals import bills_router, router as goals_router, rules_router
from routes.holdings import router as holdings_router
from routes.import_route import router as import_router
from routes.liabilities import router as liabilities_router
from routes.reports import router as reports_router
from routes.transactions import router as transactions_router

app = FastAPI(title="FlowLedger API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(InternalTokenMiddleware)

app.include_router(accounts_router)
app.include_router(categories_router)
app.include_router(transactions_router)
app.include_router(budgets_router)
app.include_router(dashboard_router)
app.include_router(holdings_router)
app.include_router(liabilities_router)
app.include_router(goals_router)
app.include_router(bills_router)
app.include_router(rules_router)
app.include_router(import_router)
app.include_router(reports_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "flowledger-api"}


@app.on_event("startup")
def on_startup():
    logger.info("FlowLedger API 启动 internal_auth=%s", bool(_expected_token()))
