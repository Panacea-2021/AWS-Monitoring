
import os
import time
import json
import logging
import html

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from urllib.parse import urlencode

import boto3
from dotenv import load_dotenv
from botocore.exceptions import BotoCoreError, ClientError


# ==========================================
# 1. LOAD ENVIRONMENT VARIABLES
# ==========================================

load_dotenv()

AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

CHECK_INTERVAL = int(
    os.getenv("CHECK_INTERVAL_SECONDS", "7200")
)

IST = ZoneInfo("Asia/Kolkata")


# ==========================================
# 2. LOGGING
# ==========================================

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ==========================================
# 3. AWS COST EXPLORER CONNECTION
# ==========================================

session = boto3.Session(
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

cost_client = session.client(
    "ce",
    region_name="us-east-1"
)


# ==========================================
# 4. TELEGRAM MESSAGE FUNCTION
# ==========================================

def send_telegram_message(message):

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode("utf-8")

    request = Request(
        url,
        data=payload,
        method="POST"
    )

    with urlopen(request, timeout=20) as response:

        result = json.loads(
            response.read().decode("utf-8")
        )

        if not result.get("ok"):
            raise RuntimeError(
                f"Telegram API error: {result}"
            )

    logger.info("Telegram notification sent successfully")


# ==========================================
# 5. AWS SERVICE CATEGORIES
# ==========================================

SERVICE_MAPPING = {

    "S3": [
        "Amazon Simple Storage Service",
        "Amazon S3",
        "S3"
    ],

    "Relational Database Service": [
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


# ==========================================
# 6. GET DAILY SERVICE-WISE COSTS
# ==========================================

def get_daily_service_costs(report_date):

    next_date = report_date + timedelta(days=1)

    service_costs = {}

    next_token = None

    while True:

        params = {

            "TimePeriod": {
                "Start": report_date.isoformat(),
                "End": next_date.isoformat()
            },

            "Granularity": "DAILY",

            "Metrics": ["UnblendedCost"],

            "GroupBy": [
                {
                    "Type": "DIMENSION",
                    "Key": "SERVICE"
                }
            ]
        }

        if next_token:
            params["NextPageToken"] = next_token

        response = cost_client.get_cost_and_usage(
            **params
        )

        results = response.get("ResultsByTime", [])

        if results:

            for group in results[0].get("Groups", []):

                service_name = group["Keys"][0]

                amount = float(
                    group["Metrics"]["UnblendedCost"]["Amount"]
                )

                service_costs[service_name] = (
                    service_costs.get(service_name, 0.0)
                    + amount
                )

        next_token = response.get("NextPageToken")

        if not next_token:
            break

    return service_costs


# ==========================================
# 7. FORMAT SERVICE-WISE COSTS
# ==========================================

def format_service_costs(raw_service_costs):

    final_costs = {}

    used_services = set()

    # Initialize all requested categories to zero
    for display_name in SERVICE_MAPPING:
        final_costs[display_name] = 0.0

    # Match AWS service names to display categories
    for actual_name, amount in raw_service_costs.items():

        matched = False

        actual_normalized = actual_name.lower().strip()

        for display_name, aliases in SERVICE_MAPPING.items():

            for alias in aliases:

                alias_normalized = alias.lower().strip()

                if actual_normalized == alias_normalized:

                    final_costs[display_name] += amount

                    used_services.add(actual_name)

                    matched = True

                    break

            if matched:
                break

        # Unmatched services are added to Others later

    # Calculate remaining services
    others_cost = sum(
        amount
        for service, amount in raw_service_costs.items()
        if service not in used_services
    )

    final_costs["Others"] = others_cost

    return final_costs


# ==========================================
# 8. GET DAILY TOTAL COST
# ==========================================

def get_daily_total(report_date):

    next_date = report_date + timedelta(days=1)

    response = cost_client.get_cost_and_usage(

        TimePeriod={
            "Start": report_date.isoformat(),
            "End": next_date.isoformat()
        },

        Granularity="DAILY",

        Metrics=["UnblendedCost"]
    )

    results = response.get("ResultsByTime", [])

    if not results:
        return 0.0, "USD"

    total_data = results[0].get(
        "Total", {}
    ).get("UnblendedCost", {})

    amount = float(total_data.get("Amount", 0))

    currency = total_data.get("Unit", "USD")

    return amount, currency


# ==========================================
# 9. GET CURRENT MONTH TOTAL COST
# ==========================================

def get_monthly_total():

    today = datetime.now(IST).date()

    month_start = today.replace(day=1)

    tomorrow = today + timedelta(days=1)

    response = cost_client.get_cost_and_usage(

        TimePeriod={
            "Start": month_start.isoformat(),
            "End": tomorrow.isoformat()
        },

        Granularity="MONTHLY",

        Metrics=["UnblendedCost"]
    )

    results = response.get("ResultsByTime", [])

    if not results:
        return 0.0, "USD"

    total_data = results[0].get(
        "Total", {}
    ).get("UnblendedCost", {})

    amount = float(total_data.get("Amount", 0))

    currency = total_data.get("Unit", "USD")

    return amount, currency


# ==========================================
# 10. SEND DAILY COST REPORT
# ==========================================

def send_cost_report():

    # Get current India date
    today = datetime.now(IST).date()

    # Fetch TODAY's cost
    report_date = today

    # Get service-wise cost
    raw_service_costs = get_daily_service_costs(
        report_date
    )

    service_costs = format_service_costs(
        raw_service_costs
    )

    # Get daily total
    daily_total, currency = get_daily_total(
        report_date
    )

    # Get current month total
    monthly_total, monthly_currency = get_monthly_total()

    # Current India time
    current_time = datetime.now(
        IST
    ).strftime("%I:%M:%S %p IST")

    # Build service breakdown
    service_message = ""

    for service, amount in service_costs.items():

        service_message += (
            f"• {html.escape(service)}: "
            f"<b>{amount:.2f} "
            f"{html.escape(currency)}</b>\n"
        )

    # Final Telegram message
    message = (

        "<b>💰 AWS COST REPORT</b>\n\n"

        f"<b>📅 Report Date: {report_date.strftime('%b-%d-%Y')}</b>\n\n"

        "<b>📊 SERVICE-WISE COST BREAKDOWN</b>\n\n"

        f"{service_message}\n"

        "<b>💵 Total costs</b>\n"
        f"<b>{daily_total:.2f} "
        f"{html.escape(currency)}</b>\n\n"

        "<b>📈 Current Month Total Cost</b>\n"
        f"<b>{monthly_total:.2f} "
        f"{html.escape(monthly_currency)}</b>\n\n"

        f"<b>🕒 Updated Check:</b> {current_time}\n\n"

        "<b>⏱ Next Notification: 2 Hours</b>"
    )

    send_telegram_message(message)

    logger.info(
        "Report sent | Date: %s | Daily: %.2f | Monthly: %.2f",
        report_date,
        daily_total,
        monthly_total
    )


# ==========================================
# 11. MAIN APPLICATION
# ==========================================

def main():

    logger.info(
        "AWS Daily Cost Monitoring Bot Started"
    )

    try:

        send_telegram_message(

            "<b>✅ AWS Cost Monitoring Bot Started!</b>\n\n"

            "<b>Monitoring:</b>\n"
            "• Daily AWS Cost\n"
            "• S3\n"
            "• Relational Database Service\n"
            "• EC2-Instances\n"
            "• Cost Explorer\n"
            "• EC2-Other\n"
            "• VPC\n"
            "• CloudTrail\n"
            "• CloudShell\n"
            "• Glue\n"
            "• Others\n"
            "• Current Month Total Cost\n\n"

            "<b>Notification Frequency:</b> Every 2 Hours"
        )

    except Exception:

        logger.exception(
            "Startup Telegram notification failed"
        )

    while True:

        try:

            send_cost_report()

        except (ClientError, BotoCoreError) as error:

            logger.exception("AWS API error")

            try:

                send_telegram_message(
                    "<b>❌ AWS Cost API Error</b>\n"
                    f"Error: {html.escape(str(error))}"
                )

            except Exception:

                logger.exception(
                    "Failed to send AWS error notification"
                )

        except Exception as error:

            logger.exception("Unexpected error")

            try:

                send_telegram_message(
                    "<b>❌ Monitoring Error</b>\n"
                    f"Error: {html.escape(str(error))}"
                )

            except Exception:

                logger.exception(
                    "Failed to send error notification"
                )

        logger.info(
            "Next cost report in %s seconds",
            CHECK_INTERVAL
        )

        time.sleep(CHECK_INTERVAL)


# ==========================================
# 12. APPLICATION ENTRY POINT
# ==========================================

if __name__ == "__main__":

    main()
