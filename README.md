# AWS EC2 + Cost Telegram Monitor

Python bot that checks EC2 instance states and CPU utilization every 5 minutes, sends state-change/high-CPU alerts to Telegram, and sends a daily AWS Cost Explorer report.

## Local setup

1. Install Python 3.10+.
2. Open this folder in VS Code.
3. Create a virtual environment (optional but recommended): `python -m venv .venv`
4. Activate it on Windows: `.venv\\Scripts\\activate`
5. Install dependencies: `pip install -r requirements.txt`
6. Copy `.env.example` to `.env` and fill in your values. The script does not automatically load `.env`; in local Windows PowerShell set the variables in the terminal, or install `python-dotenv` and add `load_dotenv()` if you prefer `.env` loading.
7. Run: `python main.py`

## AWS IAM permissions

Create an IAM policy named `AWSMonitoringReadOnlyPolicy` with:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid":"EC2ReadOnly","Effect":"Allow","Action":["ec2:DescribeInstances"],"Resource":"*"},
    {"Sid":"CloudWatchReadOnly","Effect":"Allow","Action":["cloudwatch:GetMetricStatistics"],"Resource":"*"},
    {"Sid":"CostExplorerReadOnly","Effect":"Allow","Action":["ce:GetCostAndUsage"],"Resource":"*"}
  ]
}
```

Attach it to a dedicated IAM user and create an access key. Do not use root credentials. Enable Cost Explorer in the AWS Billing console. Cost Explorer data is delayed; the daily report uses yesterday and month-to-date through yesterday. Amounts are USD.

## Telegram

Create a bot with `@BotFather` using `/newbot`, save its token, open the bot and send `/start`. To find your chat ID, visit `https://api.telegram.org/botYOUR_TOKEN/getUpdates` after sending a message to the bot; use `message.chat.id`.

## Render

Create a **Background Worker** from your Git repository.

- Build command: `pip install -r requirements.txt`
- Start command: `python main.py`

Add these environment variables in Render:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION` (the region where your EC2 instances run, e.g. `ap-south-1`)
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `CHECK_INTERVAL_SECONDS` = `300`
- `CPU_ALERT_THRESHOLD` = `80`
- `COST_REPORT_INTERVAL_SECONDS` = `86400`

Cost Explorer client is configured for `us-east-1` in the code. Keep your AWS secrets out of GitHub; set them only in Render's Environment page.

## Notes

- CPU metrics may be unavailable briefly after an instance starts; basic EC2 state monitoring still works.
- The bot remembers prior instance states in memory. Restarting the worker resets that short-term history.
- This bot is read-only: it does not start, stop, or modify EC2 resources.
