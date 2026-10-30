
import os
import time
import logging
import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlencode

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# --------------------------------
# 1. CONFIGURATION
# --------------------------------

AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

CHECK_INTERVAL = 7200  # 2 hours

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# --------------------------------
# 2. AWS CONNECTION
# --------------------------------

session = boto3.Session(
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# Cost Explorer API is accessed through us-east-1
cost_client = session.client(
    "ce",
    region_name="us-east-1"
)

# --------------------------------
# 3. TELEGRAM NOTIFICATION
# --------------------------------

def send_telegram_message(message):

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
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
            raise RuntimeError("Telegram message failed")

    logger.info("Telegram notification sent successfully")


# --------------------------------
# 4. GET AWS DAILY COST
# --------------------------------

def get_daily_aws_cost():

    today = datetime.now(timezone.utc).date()

    tomorrow = today + timedelta(days=1)

    response = cost_client.get_cost_and_usage(

        TimePeriod={
            "Start": today.isoformat(),
            "End": tomorrow.isoformat()
        },

        Granularity="DAILY",

        Metrics=[
            "UnblendedCost"
        ]
    )

    results = response.get("ResultsByTime", [])

    if not results:
        return today, 0.0, "USD"

    amount_data = (
        results[0]
        .get("Total", {})
        .get("UnblendedCost", {})
    )

    amount = float(amount_data.get("Amount", 0))

    currency = amount_data.get("Unit", "USD")

    return today, amount, currency


# --------------------------------
# 5. SEND COST REPORT
# --------------------------------

def send_daily_cost_report():

    today, cost, currency = get_daily_aws_cost()

    current_time = datetime.now(
        timezone.utc
    ).strftime("%H:%M UTC")

    message = f"""
💰 AWS DAILY COST REPORT

📅 Date: {today}

💵 Total AWS Cost: {cost:.4f} {currency}

🕒 Updated Check: {current_time}

⏱ Next Notification: 2 Hours

📊 Service: AWS Cost Explorer
"""

    send_telegram_message(message)

    logger.info(
        "Daily AWS cost: %.4f %s",
        cost,
        currency
    )


# --------------------------------
# 6. MAIN MONITORING LOOP
# --------------------------------

def main():

    logger.info("AWS Daily Cost Bot Started")

    try:
        send_telegram_message(
            "✅ AWS Daily Cost Monitoring Bot Started!\n\n"
            "Monitoring: Total AWS Daily Cost\n"
            "Notification Frequency: Every 2 Hours"
        )
    except Exception:
        logger.exception("Startup Telegram message failed")

    while True:

        try:

            send_daily_cost_report()

        except (ClientError, BotoCoreError) as error:

            logger.exception("AWS API error")

            try:
                send_telegram_message(
                    "❌ AWS Cost API Error\n"
                    f"Error: {type(error).__name__}"
                )
            except Exception:
                logger.exception("Telegram error notification failed")

        except Exception as error:

            logger.exception("Unexpected error")

            try:
                send_telegram_message(
                    "❌ Monitoring Error\n"
                    f"Error: {type(error).__name__}"
                )
            except Exception:
                logger.exception("Telegram error notification failed")

        logger.info("Next check in 2 hours")

        time.sleep(CHECK_INTERVAL)


# --------------------------------
# 7. APPLICATION ENTRY POINT
# --------------------------------

if __name__ == "__main__":

    main()
