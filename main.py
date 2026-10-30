import datetime
import os
import time
import boto3
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram_message(message):
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
  try:
    response = requests.post(url, json=payload)
    return response.json()
  except Exception as e:
    print(f"Error sending telegram message: {e}")


def get_aws_cost():
  client = boto3.client(
      "ce",
      region_name=os.environ.get("AWS_REGION", "us-east-1"),
      aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
      aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
  )

  today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
  # Month start date for overall total cost
  month_start = datetime.datetime.utcnow().strftime("%Y-%m-01")

  try:
    # 1. Overall Month-to-Date Total Cost
    response_total = client.get_cost_and_usage(
        TimePeriod={"Start": month_start, "End": today},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )
    total_cost = float(
        response_total["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"]
    )

    # 2. Today's Cost (Every 2 hours update kosam)
    response_today = client.get_cost_and_usage(
        TimePeriod={"Start": today, "End": today},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )
    today_cost = float(
        response_today["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"]
    )

    return total_cost, today_cost
  except Exception as e:
    print(f"Error fetching AWS cost: {e}")
    return 0.0, 0.0


def send_daily_cost_report():
  total_cost, today_cost = get_aws_cost()
  current_time = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

  message = (
      "💰 *AWS COST MONITORING REPORT*\n\n"
      f"📅 *Current Time:* {current_time}\n"
      f"💵 *Overall Total Cost (This Month):* ${total_cost:.4f} USD\n"
      f"⏱ *Today's Cost (Every 2 Hrs Check):* ${today_cost:.4f} USD\n\n"
      "📊 *Service:* AWS Cost Explorer"
  )
  send_telegram_message(message)


if __name__ == "__main__":
  send_telegram_message("✅ AWS Cost Monitoring Bot Started as Background Worker!")
  while True:
    send_daily_cost_report()
    time.sleep(7200)  # 2 Hours interval