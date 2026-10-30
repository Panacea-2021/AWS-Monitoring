
import os
import time
import logging
import html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import boto3
import requests
from dotenv import load_dotenv
from botocore.exceptions import BotoCoreError, ClientError

# Load environment variables
load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_GROUP_CHAT_ID = os.getenv("TELEGRAM_GROUP_CHAT_ID")

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "7200"))

IST = ZoneInfo("Asia/Kolkata")

# Logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Validate required configuration
required_values = {
    "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
    "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
}

missing = [key for key, value in required_values.items() if not value]

if missing:
    raise ValueError(f"Missing environment variables: {', '.join(missing)}")

if CHECK_INTERVAL <= 0:
    raise ValueError("CHECK_INTERVAL_SECONDS must be greater than zero")

# AWS Cost Explorer client
session = boto3.Session(
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

cost_client = session.client("ce", region_name="us-east-1")


# Telegram: send to personal chat and group
def send_telegram_message(message):
    chat_ids = list(dict.fromkeys([
        TELEGRAM_CHAT_ID,
        TELEGRAM_GROUP_CHAT_ID
    ]))

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for chat_id in chat_ids:
        if not chat_id:
            continue

        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()

            if not result.get("ok"):
                raise RuntimeError(str(result))

            logger.info("Telegram message sent to chat ID: %s", chat_id)

        except requests.RequestException:
            logger.exception(
                "Failed to send Telegram message to chat ID: %s",
                chat_id
            )
            raise


# AWS service name mapping
SERVICE_MAPPING = {
    "S3": [
        "Amazon Simple Storage Service",
        "Amazon S3",
        "S3"
    ],
    "RDS": [
        "Amazon Relational Database Service",
        "Relational Database Service"
    ],
    "EC2-Instances": [
        "EC2 - Instances",
        "EC2-Instances",
        "Amazon Elastic Compute Cloud - Compute"
    ],
    "Cost Explorer": [
        "AWS Cost Explorer",
        "Cost Explorer"
    ],
    "EC2-Other": [
        "EC2 - Other",
        "EC2-Other"
    ],
    "VPC": [
        "Amazon Virtual Private Cloud",
        "Amazon VPC",
        "VPC"
    ],
    "CloudTrail": [
        "AWS CloudTrail",
        "Amazon CloudTrail",
        "CloudTrail"
    ],
    "CloudShell": [
        "AWS CloudShell",
        "CloudShell"
    ],
    "Glue": [
        "AWS Glue",
        "Glue"
    ]
}


def get_daily_service_costs(report_date):
    start_date = report_date.strftime("%Y-%m-%d")
    end_date = (report_date + timedelta(days=1)).strftime("%Y-%m-%d")

    response = cost_client.get_cost_and_usage(
        TimePeriod={
            "Start": start_date,
            "End": end_date
        },
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[
            {
                "Type": "DIMENSION",
                "Key": "SERVICE"
            }
        ]
    )

    raw_costs = {}

    for period in response.get("ResultsByTime", []):
        for group in period.get("Groups", []):
            service_name = group["Keys"][0]
            amount = float(
                group["Metrics"]["UnblendedCost"]["Amount"]
            )
            unit = group["Metrics"]["UnblendedCost"]["Unit"]

            raw_costs[service_name] = (
                raw_costs.get(service_name, 0.0) + amount
            )

    return raw_costs, unit if raw_costs else "USD"


def format_service_costs(raw_service_costs):
    formatted = {name: 0.0 for name in SERVICE_MAPPING}
    formatted["Others"] = 0.0

    for service_name, amount in raw_service_costs.items():
        matched = False
        normalized_name = service_name.strip().lower()

        for category, aliases in SERVICE_MAPPING.items():
            if normalized_name in [alias.lower() for alias in aliases]:
                formatted[category] += amount
                matched = True
                break

        if not matched:
            formatted["Others"] += amount

    return formatted


def get_daily_total(report_date):
    start_date = report_date.strftime("%Y-%m-%d")
    end_date = (report_date + timedelta(days=1)).strftime("%Y-%m-%d")

    response = cost_client.get_cost_and_usage(
        TimePeriod={
            "Start": start_date,
            "End": end_date
        },
        Granularity="DAILY",
        Metrics=["UnblendedCost"]
    )

    results = response.get("ResultsByTime", [])

    if not results:
        return 0.0, "USD"

    metric = results[0]["Total"]["UnblendedCost"]

    return float(metric["Amount"]), metric["Unit"]


def get_monthly_total():
    today = datetime.now(IST).date()

    start_date = today.replace(day=1).strftime("%Y-%m-%d")
    end_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")

    response = cost_client.get_cost_and_usage(
        TimePeriod={
            "Start": start_date,
            "End": end_date
        },
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"]
    )

    results = response.get("ResultsByTime", [])

    if not results:
        return 0.0, "USD"

    metric = results[0]["Total"]["UnblendedCost"]

    return float(metric["Amount"]), metric["Unit"]


def send_cost_report():
    today = datetime.now(IST).date()

    # Current day's cost
    report_date = today

    logger.info("Fetching AWS cost report for %s", report_date)

    raw_service_costs, unit = get_daily_service_costs(report_date)

    service_costs = format_service_costs(raw_service_costs)

    daily_total, daily_unit = get_daily_total(report_date)

    monthly_total, monthly_unit = get_monthly_total()

    updated_time = datetime.now(IST).strftime("%I:%M %p")

    message = (
        "📊 <b>AWS COST REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 <b>Report Date:</b> {report_date.strftime('%b-%d-%Y')}\n\n"
        "💰 <b>DAILY SERVICE COST</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )

    for service_name, amount in service_costs.items():
        safe_name = html.escape(service_name)
        message += f"• {safe_name}: <b>{amount:.4f} {unit}</b>\n"

    message += (
        "\n━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Daily Total:</b> {daily_total:.4f} {daily_unit}\n"
        f"📅 <b>Current Month Total:</b> "
        f"{monthly_total:.4f} {monthly_unit}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🕒 <b>Updated Check:</b> {updated_time} IST\n"
        "⏱️ <b>Next Check:</b> Every 2 Hours"
    )

    send_telegram_message(message)

    logger.info("Cost report sent successfully")


def main():
    logger.info("AWS Cost Monitoring Bot started")

    send_telegram_message(
        "✅ <b>AWS Cost Monitoring Bot Started</b>\n"
        "📊 Reports will be sent every 2 hours.\n"
        "👤 Personal chat and group notifications enabled."
    )

    while True:
        try:
            send_cost_report()

        except (BotoCoreError, ClientError):
            logger.exception("AWS Cost Explorer error")

        except Exception:
            logger.exception("Unexpected error")

        logger.info("Waiting %s seconds for next report", CHECK_INTERVAL)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
