## AWS IAM Permissions

Create an IAM policy named `AWSMonitoringReadOnlyPolicy` with the following permission:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CostExplorerReadOnly",
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage"
      ],
      "Resource": "*"
    }
  ]
}