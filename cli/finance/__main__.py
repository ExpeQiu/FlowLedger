"""FlowLedger CLI — 通过 FastAPI 操作财务数据"""

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import typer

app = typer.Typer(help="FlowLedger 个人财务 CLI")
API_URL = os.getenv("API_URL", "http://localhost:9011")


def client() -> httpx.Client:
    return httpx.Client(base_url=API_URL, timeout=30)


@app.command()
def today():
    """今日收支摘要"""
    with client() as c:
        r = c.get("/api/transactions", params={"limit": 20})
        r.raise_for_status()
        txs = r.json()
        today_str = date.today().isoformat()
        today_txs = [t for t in txs if t["date"] == today_str]
        income = sum(Decimal(t["amount"]) for t in today_txs if t["type"] == "income")
        expense = sum(Decimal(t["amount"]) for t in today_txs if t["type"] == "expense")
        typer.echo(f"今日收入: ¥{income}")
        typer.echo(f"今日支出: ¥{expense}")
        typer.echo(f"净额: ¥{income - expense}")
        for t in today_txs:
            sign = "+" if t["type"] == "income" else "-"
            typer.echo(f"  {t['date']} {t.get('merchant','')} {sign}¥{t['amount']}")


@app.command("add")
def add_expense(
    amount: float = typer.Option(..., "--amount"),
    category: str = typer.Option(..., "--category"),
    note: str = typer.Option("", "--note"),
    account: str = typer.Option("支付宝", "--account"),
):
    """快速记账"""
    with client() as c:
        accounts = c.get("/api/accounts").json()
        categories = c.get("/api/categories").json()
        acc = next((a for a in accounts if a["name"] == account), accounts[0] if accounts else None)
        cat = next((x for x in categories if x["name"] == category), None)
        if not acc:
            typer.echo("无可用账户", err=True)
            raise typer.Exit(1)
        payload = {
            "type": "expense",
            "amount": amount,
            "date": date.today().isoformat(),
            "account_id": acc["id"],
            "category_id": cat["id"] if cat else None,
            "note": note,
            "merchant": note,
        }
        r = c.post("/api/transactions", json=payload)
        r.raise_for_status()
        typer.echo(f"已记录: {category} -¥{amount}")


@app.command("import")
def import_csv(
    file: Path = typer.Argument(..., help="CSV 文件路径"),
    source: str = typer.Option("csv", "--source"),
    account: str = typer.Option("支付宝", "--account"),
):
    """导入账单 CSV"""
    with client() as c:
        accounts = c.get("/api/accounts").json()
        acc = next((a for a in accounts if a["name"] == account), accounts[0] if accounts else None)
        if not acc:
            typer.echo("无可用账户", err=True)
            raise typer.Exit(1)
        with open(file, "rb") as f:
            r = c.post(
                "/api/import/csv",
                files={"file": (file.name, f, "text/csv")},
                data={"source": source, "account_id": acc["id"]},
            )
        r.raise_for_status()
        result = r.json()
        typer.echo(f"导入完成: {result['imported']} 条, 跳过 {result['skipped']} 条重复")


budget_app = typer.Typer()
app.add_typer(budget_app, name="budget")


@budget_app.command("status")
def budget_status(month: str = typer.Option(None, "--month")):
    """查看预算状态"""
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    with client() as c:
        r = c.get("/api/budgets/status", params={"month": month})
        r.raise_for_status()
        for b in r.json():
            typer.echo(f"{b.get('category_name','?')}: ¥{b.get('spent',0)} / ¥{b['amount']} ({b.get('usage_pct',0)}%)")


portfolio_app = typer.Typer()
app.add_typer(portfolio_app, name="portfolio")


@portfolio_app.command("summary")
def portfolio_summary(as_of: str = typer.Option("today", "--as-of")):
    """投资组合摘要"""
    with client() as c:
        r = c.get("/api/holdings/summary")
        r.raise_for_status()
        s = r.json()
        typer.echo(f"投资总资产: ¥{s['total_value']}")
        typer.echo(f"持仓市值: ¥{s.get('holdings_value', 0)}")
        typer.echo(f"闲置现金: ¥{s.get('cash_balance', 0)}")
        typer.echo(f"持仓成本: ¥{s['total_cost']}")
        typer.echo(f"持仓浮盈: ¥{s['profit']} ({s['profit_pct']}%)")
        if s.get("validation_ok") is False:
            typer.echo("警告: 投资账户余额与持仓不一致", err=True)
        for h in s["holdings"]:
            typer.echo(f"  {h['name']}: ¥{h.get('market_value',0)} ({h.get('profit_pct',0)}%)")


export_app = typer.Typer()
app.add_typer(export_app, name="export")


@export_app.command("report")
def export_report(
    month: str = typer.Option(..., "--month"),
    format: str = typer.Option("xlsx", "--format"),
):
    """导出报表"""
    with client() as c:
        r = c.post("/api/reports/export", params={"month": month, "format": format})
        r.raise_for_status()
        out = Path(f"report-{month}.{format}")
        out.write_bytes(r.content)
        typer.echo(f"已导出: {out}")


if __name__ == "__main__":
    app()
