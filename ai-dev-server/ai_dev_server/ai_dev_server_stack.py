from aws_cdk import (
    Stack,
    CfnParameter,
    CfnOutput,
    aws_ec2 as ec2,
    aws_iam as iam,
)
from constructs import Construct


class AiDevServerStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Parameters ─────────────────────────────────────────────────────────

        key_pair_name = CfnParameter(self, "KeyPairName",
            type="String",
            description="Name of an existing EC2 key pair for SSH access",
        )

        instance_type = CfnParameter(self, "InstanceType",
            type="String",
            default="t3.xlarge",
            description="EC2 instance type (default: t3.xlarge — 4 vCPU, 16GB RAM)",
        )

        ebs_size = CfnParameter(self, "EbsSize",
            type="Number",
            default=20,
            description="Root EBS volume size in GB (default: 20)",
        )

        allowed_ssh_cidr = CfnParameter(self, "AllowedSshCidr",
            type="String",
            default="0.0.0.0/0",
            description="CIDR range allowed to SSH (default: 0.0.0.0/0 — restrict to your IP for better security)",
        )

        # ── VPC ────────────────────────────────────────────────────────────────
        # Use provided VPC ID (via -c vpc_id=vpc-xxx) or fall back to default VPC.
        # VPC lookup must be concrete at synth time — use context, not CfnParameter.

        vpc_id_ctx = self.node.try_get_context("vpc_id")

        if vpc_id_ctx:
            vpc = ec2.Vpc.from_lookup(self, "Vpc", vpc_id=vpc_id_ctx)
        else:
            vpc = ec2.Vpc.from_lookup(self, "Vpc", is_default=True)

        # ── Security Group ─────────────────────────────────────────────────────

        sg = ec2.SecurityGroup(self, "AiDevServerSG",
            vpc=vpc,
            description="AI Dev Server - SSH access only",
            allow_all_outbound=True,
        )

        sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(allowed_ssh_cidr.value_as_string),
            connection=ec2.Port.tcp(22),
            description="SSH",
        )

        # ── IAM Role ───────────────────────────────────────────────────────────

        role = iam.Role(self, "AiDevServerRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="AI Dev Server - Bedrock and AgentCore access via IAM role (no API keys on server)",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSCloudFormationFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("IAMFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSLambda_FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLogsFullAccess"),
            ],
        )

        # ── AMI — Amazon Linux 2023 ────────────────────────────────────────────

        ami = ec2.MachineImage.latest_amazon_linux2023()

        # ── User Data ──────────────────────────────────────────────────────────
        # Runs on first boot — installs Node.js, Claude Code, Python stack

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "set -eux",
            "# ── System update ──────────────────────────────────────────────",
            "dnf update -y",
            "dnf install -y git",

            "# ── AWS CLI ────────────────────────────────────────────────────",
            "dnf install -y awscli",

            "# ── Node.js 20 ─────────────────────────────────────────────────",
            "curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -",
            "dnf install -y nodejs",

            "# ── Claude Code CLI ────────────────────────────────────────────",
            "npm install -g @anthropic-ai/claude-code",

            "# ── AgentCore CLI ───────────────────────────────────────────────",
            "npm install -g @aws/agentcore",

            "# ── Python + boto3 + Strands ───────────────────────────────────",
            "dnf install -y python3.11 python3.11-pip",
            "pip3.11 install boto3 strands-agents strands-agents-tools",

            "# ── uv (Python package manager — required by AgentCore CLI) ────",
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            'echo \'export PATH="$HOME/.local/bin:$PATH"\' >> /home/ec2-user/.bashrc',

            "# ── Clone aiml-on-aws repo (scripts, tests) ────────────────────",
            "git clone https://github.com/jdluther2025/aiml-on-aws.git /home/ec2-user/aiml-on-aws",
            "chown -R ec2-user:ec2-user /home/ec2-user/aiml-on-aws",

            "# ── Signal completion ───────────────────────────────────────────",
            'echo "AI Dev Server setup complete" >> /var/log/ai-dev-server-setup.log',
        )

        # ── EC2 Instance ───────────────────────────────────────────────────────

        instance = ec2.Instance(self, "AiDevServer",
            instance_type=ec2.InstanceType(instance_type.value_as_string),
            machine_image=ami,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=sg,
            role=role,
            key_pair=ec2.KeyPair.from_key_pair_name(self, "KeyPair", key_pair_name.value_as_string),
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        ebs_size.value_as_number,
                        encrypted=True,
                    ),
                )
            ],
            user_data=user_data,
        )

        # ── Elastic IP ─────────────────────────────────────────────────────────

        eip = ec2.CfnEIP(self, "AiDevServerEIP",
            instance_id=instance.instance_id,
        )

        # ── Outputs ────────────────────────────────────────────────────────────

        CfnOutput(self, "PublicIp",
            value=eip.ref,
            description="AI Dev Server public IP address",
        )

        CfnOutput(self, "SshCommand",
            value=f"ssh -i ~/.ssh/{key_pair_name.value_as_string}.pem ec2-user@{eip.ref}",
            description="SSH command to connect to the AI Dev Server",
        )

        CfnOutput(self, "InstanceId",
            value=instance.instance_id,
            description="EC2 Instance ID",
        )
