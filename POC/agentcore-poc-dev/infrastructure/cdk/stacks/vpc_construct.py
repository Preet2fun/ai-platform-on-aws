"""
Three-Tier VPC Construct — exact CDK port of the Comprinno Terraform VPC module
===============================================================================
This construct reproduces `VPC-CODE-MODULE/modules/vpc/vpc.tf` resource-for-resource
using low-level CloudFormation (Cfn*) constructs, so the deployed topology is an
exact match for what the Terraform module provisions — including the number of
route tables (3 shared per-tier tables, NOT one-per-subnet).

Terraform → CDK resource mapping (for 3 CIDRs per tier / 3 AZs):
  aws_vpc.vpc                         → ec2.CfnVPC                       (1)
  aws_subnet.public_subnets           → ec2.CfnSubnet                    (3, map_public_ip=true)
  aws_subnet.private_app_subnets      → ec2.CfnSubnet                    (3)
  aws_subnet.private_db_subnets       → ec2.CfnSubnet                    (3)
  aws_internet_gateway.igw            → ec2.CfnInternetGateway + attach  (1)
  aws_eip.natA                        → ec2.CfnEIP                       (1)
  aws_nat_gateway.ngwA                → ec2.CfnNatGateway (public[0])    (1)
  aws_route_table.rtb_public          → ec2.CfnRouteTable                (1, shared)
    aws_route.public_route            → ec2.CfnRoute 0.0.0.0/0 → IGW
    aws_route_table_association (×3)  → ec2.CfnSubnetRouteTableAssociation
  aws_route_table.rtb_private_app     → ec2.CfnRouteTable                (1, shared)
    aws_route.private_route           → ec2.CfnRoute 0.0.0.0/0 → NAT
    aws_route_table_association (×3)  → ec2.CfnSubnetRouteTableAssociation
  aws_route_table.rtb_private_db      → ec2.CfnRouteTable                (1, shared, no route)
    aws_route_table_association (×3)  → ec2.CfnSubnetRouteTableAssociation

Exact CIDR layout (matches examples.tfvars):
  public      : 10.0.0.0/20,  10.0.16.0/20,  10.0.32.0/20
  private-app : 10.0.48.0/20, 10.0.64.0/20,  10.0.80.0/20
  private-db  : 10.0.96.0/20, 10.0.112.0/20, 10.0.128.0/20

Naming (matches the Terraform module):
  VPC dev-vpc | subnets dev-<tier>-<index> | RTs dev-<tier>-route-table
  IGW dev-IGW | NAT dev-NAT-GW | endpoint SG dev-vpc-endpoints-sg
  flow-log group /aws/dev-vpc/flowlogs | flow-log role dev-<region>-vpc-flowlogs-role
Every resource also carries an Environment=<env> tag (via CfnTag / Tags.of).

VPC endpoints & flow logs mirror vpc_endpoints.tf / vpc_flowlogs.tf. The SSM trio
and the S3 gateway endpoint are intentionally omitted (S3 is added by AlbToFargate).
"""
from typing import List

from aws_cdk import (
    Tags,
    RemovalPolicy,
    CfnTag,
    Fn,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct

PUBLIC_SUBNET_NAME = "public-subnet"
PRIVATE_APP_SUBNET_NAME = "private-app-subnet"
PRIVATE_DB_SUBNET_NAME = "private-db-subnet"

# CIDR lists per tier — identical to VPC-CODE-MODULE/examples.tfvars.
PUBLIC_CIDRS = ["10.0.0.0/20", "10.0.16.0/20", "10.0.32.0/20"]
PRIVATE_APP_CIDRS = ["10.0.48.0/20", "10.0.64.0/20", "10.0.80.0/20"]
PRIVATE_DB_CIDRS = ["10.0.96.0/20", "10.0.112.0/20", "10.0.128.0/20"]


class ThreeTierVpc(Construct):
    """Exact CDK port of the Terraform three-tier VPC module (L1 Cfn constructs).

    Exposes:
        vpc            — an ec2.IVpc view (imported via from_vpc_attributes) suitable
                         for passing to AlbToFargate's `existing_vpc`.
        vpc_id         — the CfnVPC ref.
        public_subnet_ids / private_app_subnet_ids / private_db_subnet_ids — id lists.
        endpoint_security_group — SG guarding interface endpoints (or None).
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        environment_name: str,
        region: str,
        cidr: str = "10.0.0.0/16",
        enable_cloudwatch_endpoints: bool = True,
        enable_flow_logs: bool = True,
    ) -> None:
        super().__init__(scope, id)

        self._env = environment_name
        self._region = region

        # --- VPC (aws_vpc.vpc) ---
        self._cfn_vpc = ec2.CfnVPC(
            self, "Vpc",
            cidr_block=cidr,
            enable_dns_support=True,
            enable_dns_hostnames=True,
            tags=self._tags("vpc"),
        )
        self.vpc_id = self._cfn_vpc.ref

        # --- Internet Gateway (aws_internet_gateway.igw) + attachment ---
        self._igw = ec2.CfnInternetGateway(self, "IGW", tags=self._tags("IGW"))
        ec2.CfnVPCGatewayAttachment(
            self, "VPCGWAttachment",
            vpc_id=self.vpc_id,
            internet_gateway_id=self._igw.ref,
        )

        # --- Subnets (3 per tier, one per AZ) ---
        # Fn.get_azs / select gives the AZ names in order, matching Terraform's
        # data.aws_availability_zones.available.names[count.index].
        self._public_subnets = self._make_subnets(
            PUBLIC_SUBNET_NAME, PUBLIC_CIDRS, map_public_ip=True
        )
        self._app_subnets = self._make_subnets(
            PRIVATE_APP_SUBNET_NAME, PRIVATE_APP_CIDRS, map_public_ip=False
        )
        self._db_subnets = self._make_subnets(
            PRIVATE_DB_SUBNET_NAME, PRIVATE_DB_CIDRS, map_public_ip=False
        )

        self.public_subnet_ids = [s.ref for s in self._public_subnets]
        self.private_app_subnet_ids = [s.ref for s in self._app_subnets]
        self.private_db_subnet_ids = [s.ref for s in self._db_subnets]

        # --- NAT Gateway (aws_eip.natA + aws_nat_gateway.ngwA) in public subnet[0] ---
        eip = ec2.CfnEIP(self, "NatEIP", domain="vpc", tags=self._tags("NAT-EIP"))
        self._nat = ec2.CfnNatGateway(
            self, "NatGateway",
            subnet_id=self._public_subnets[0].ref,
            allocation_id=eip.attr_allocation_id,
            tags=self._tags("NAT-GW"),
        )
        self._nat.add_dependency(self._igw)

        # --- Route tables (exactly one shared per tier) ---
        # Public RT: 0.0.0.0/0 → IGW, associated with all public subnets.
        self._rtb_public = self._route_table("PublicRouteTable", "public-route-table")
        pub_route = ec2.CfnRoute(
            self, "PublicRoute",
            route_table_id=self._rtb_public.ref,
            destination_cidr_block="0.0.0.0/0",
            gateway_id=self._igw.ref,
        )
        pub_route.add_dependency(self._igw)
        self._associate(self._public_subnets, self._rtb_public, "Public")

        # Private-app RT: 0.0.0.0/0 → NAT, associated with all app subnets.
        self._rtb_app = self._route_table("PrivateAppRouteTable", "private-app-route-table")
        ec2.CfnRoute(
            self, "PrivateAppRoute",
            route_table_id=self._rtb_app.ref,
            destination_cidr_block="0.0.0.0/0",
            nat_gateway_id=self._nat.ref,
        )
        self._associate(self._app_subnets, self._rtb_app, "PrivateApp")

        # Private-db RT: NO default route (isolated), associated with all db subnets.
        self._rtb_db = self._route_table("PrivateDbRouteTable", "private-db-route-table")
        self._associate(self._db_subnets, self._rtb_db, "PrivateDb")

        # --- ec2.IVpc view for downstream constructs (AlbToFargate, endpoints) ---
        # Imported from the concrete attributes above. AZs are the first N returned
        # by the environment; subnets are grouped by tier.
        self.vpc = ec2.Vpc.from_vpc_attributes(
            self, "VpcRef",
            vpc_id=self.vpc_id,
            vpc_cidr_block=cidr,
            availability_zones=[self._az(i) for i in range(len(PUBLIC_CIDRS))],
            public_subnet_ids=self.public_subnet_ids,
            private_subnet_ids=self.private_app_subnet_ids,
            isolated_subnet_ids=self.private_db_subnet_ids,
            public_subnet_route_table_ids=[self._rtb_public.ref] * len(PUBLIC_CIDRS),
            private_subnet_route_table_ids=[self._rtb_app.ref] * len(PRIVATE_APP_CIDRS),
            isolated_subnet_route_table_ids=[self._rtb_db.ref] * len(PRIVATE_DB_CIDRS),
        )

        # --- VPC endpoints (mirrors vpc_endpoints.tf; SSM + S3 omitted) ---
        self.endpoint_security_group = None
        if enable_cloudwatch_endpoints:
            self.endpoint_security_group = self._create_endpoint_security_group(cidr)
            self._create_cloudwatch_endpoints(self.endpoint_security_group)

        # --- Flow logs (mirrors vpc_flowlogs.tf) ---
        if enable_flow_logs:
            self._create_flow_logs()

    # ------------------------------------------------------------------ helpers

    def _name(self, suffix: str) -> str:
        return f"{self._env}-{suffix}"

    def _tags(self, name_suffix: str, tier: str = None) -> List[CfnTag]:
        """Build the Name + Environment (+ optional Tier) CfnTag list used on L1 resources."""
        tags = [
            CfnTag(key="Name", value=self._name(name_suffix)),
            CfnTag(key="Environment", value=self._env),
        ]
        if tier:
            tags.append(CfnTag(key="Tier", value=tier))
        return tags

    def _az(self, index: int) -> str:
        return Fn.select(index, Fn.get_azs(self._region))

    def _make_subnets(self, tier: str, cidrs: List[str], map_public_ip: bool) -> List[ec2.CfnSubnet]:
        """Create one CfnSubnet per CIDR (one per AZ), named ${env}-<tier>-<index>."""
        subnets = []
        for index, cidr in enumerate(cidrs):
            subnet = ec2.CfnSubnet(
                self, f"{tier}-{index}",
                vpc_id=self.vpc_id,
                cidr_block=cidr,
                availability_zone=self._az(index),
                map_public_ip_on_launch=map_public_ip,
                tags=[
                    CfnTag(key="Name", value=f"{self._env}-{tier}-{index}"),
                    CfnTag(key="Environment", value=self._env),
                    CfnTag(key="Tier", value=tier),
                ],
            )
            subnets.append(subnet)
        return subnets

    def _route_table(self, logical_id: str, name_suffix: str) -> ec2.CfnRouteTable:
        return ec2.CfnRouteTable(
            self, logical_id,
            vpc_id=self.vpc_id,
            tags=self._tags(name_suffix),
        )

    def _associate(self, subnets: List[ec2.CfnSubnet], rtb: ec2.CfnRouteTable, prefix: str) -> None:
        for index, subnet in enumerate(subnets):
            ec2.CfnSubnetRouteTableAssociation(
                self, f"{prefix}RTAssoc-{index}",
                subnet_id=subnet.ref,
                route_table_id=rtb.ref,
            )

    def _create_endpoint_security_group(self, vpc_cidr: str) -> ec2.SecurityGroup:
        """SG for interface endpoints — allows 443 from the VPC CIDR (aws_security_group.vpc_endpoints_sg)."""
        sg = ec2.SecurityGroup(
            self, "VpcEndpointsSg",
            vpc=self.vpc,
            security_group_name=self._name("vpc-endpoints-sg"),
            description="Security group for VPC Interface Endpoints",
            allow_all_outbound=True,
        )
        sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc_cidr),
            connection=ec2.Port.tcp(443),
            description="HTTPS from within the VPC to interface endpoints",
        )
        Tags.of(sg).add("Name", self._name("vpc-endpoints-sg"))
        Tags.of(sg).add("Environment", self._env)
        return sg

    def _create_cloudwatch_endpoints(self, sg: ec2.SecurityGroup) -> None:
        """CloudWatch monitoring + logs interface endpoints in the private-db subnets."""
        db_subnets = ec2.SubnetSelection(subnets=[
            ec2.Subnet.from_subnet_id(self, f"DbEpSubnet-{i}", sid)
            for i, sid in enumerate(self.private_db_subnet_ids)
        ])
        for logical_id, service, name_suffix in (
            ("MonitoringEndpoint", ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_MONITORING, "monitoring-endpoint"),
            ("LogsEndpoint", ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS, "logs-endpoint"),
        ):
            endpoint = self.vpc.add_interface_endpoint(
                logical_id,
                service=service,
                subnets=db_subnets,
                security_groups=[sg],
                private_dns_enabled=True,
            )
            Tags.of(endpoint).add("Name", self._name(name_suffix))
            Tags.of(endpoint).add("Environment", self._env)

    def _create_flow_logs(self) -> None:
        """VPC flow logs (ALL traffic) → CloudWatch, with an IAM role that mirrors
        aws_iam_role.vpc_flowlogs_role + aws_iam_role_policy.vpc_flowlogs_policy."""
        log_group = logs.LogGroup(
            self, "FlowLogsGroup",
            log_group_name=f"/aws/{self._name('vpc')}/flowlogs",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        flow_logs_role = iam.Role(
            self, "FlowLogsRole",
            role_name=f"{self._env}-{self._region}-vpc-flowlogs-role",
            assumed_by=iam.ServicePrincipal("vpc-flow-logs.amazonaws.com"),
            description="Role allowing VPC Flow Logs to publish to CloudWatch Logs",
        )
        flow_logs_role.attach_inline_policy(
            iam.Policy(
                self, "FlowLogsRolePolicy",
                policy_name=f"{self._env}-{self._region}-vpc-flowlogs-policy",
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=[
                            "logs:CreateLogGroup",
                            "logs:CreateLogStream",
                            "logs:PutLogEvents",
                            "logs:DescribeLogGroups",
                            "logs:DescribeLogStreams",
                        ],
                        resources=[log_group.log_group_arn, f"{log_group.log_group_arn}:*"],
                    )
                ],
            )
        )

        ec2.CfnFlowLog(
            self, "FlowLog",
            resource_id=self.vpc_id,
            resource_type="VPC",
            traffic_type="ALL",
            deliver_logs_permission_arn=flow_logs_role.role_arn,
            log_group_name=log_group.log_group_name,
            tags=self._tags("vpc-flowlog"),
        )
