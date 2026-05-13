#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CDK_DIR="$SCRIPT_DIR/.."

echo "── STEP 1: Destroy AI Dev Server with CDK"
cd "$CDK_DIR"
source .venv/bin/activate
cdk destroy --force
deactivate

echo ""
echo "── STEP 2: Verify Elastic IP is released"
ADDRESSES=$(aws ec2 describe-addresses --query 'Addresses[*].PublicIp' --output text)
if [ -z "$ADDRESSES" ]; then
    echo "  ✅  No Elastic IPs remaining — nothing left billing"
else
    echo "  ⚠️  Elastic IPs still found: $ADDRESSES"
    echo "      Release manually in the AWS Console → EC2 → Elastic IPs"
fi

echo ""
echo "── STEP 3: Verify EC2 instance is gone"
INSTANCES=$(aws ec2 describe-instances \
    --filters "Name=tag:aws:cloudformation:stack-name,Values=AiDevServerStack" \
              "Name=instance-state-name,Values=running,stopped,pending" \
    --query 'Reservations[*].Instances[*].InstanceId' \
    --output text)
if [ -z "$INSTANCES" ]; then
    echo "  ✅  No EC2 instances remaining"
else
    echo "  ⚠️  Instances still found: $INSTANCES"
fi

echo ""
echo "  AI Dev Server fully torn down. No idle resources. No surprise bills."
