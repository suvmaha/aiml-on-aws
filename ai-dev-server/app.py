#!/usr/bin/env python3
import os
import aws_cdk as cdk
from ai_dev_server.ai_dev_server_stack import AiDevServerStack

app = cdk.App()

AiDevServerStack(app, "AiDevServerStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT", "325104839471"),
        region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
    ),
)

app.synth()
