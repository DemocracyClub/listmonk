import typing
from pathlib import Path

import aws_cdk
import boto3
from aws_cdk import (
    Environment,
    Stack,
    Duration,
    aws_apigateway,
    aws_certificatemanager,
    aws_cloudfront,
    aws_cloudfront_origins,
    aws_cloudfront_origins,
    aws_iam,
    aws_lambda,
    aws_lambda_python_alpha,
    aws_route53,
    aws_route53_targets,
    aws_ssm,
    aws_ecs,
    aws_ecs_patterns,
    aws_elasticloadbalancingv2 as elbv2,
    aws_events,
    aws_events_targets,
)
from aws_cdk.aws_cloudfront import EdgeLambda
from aws_cdk.aws_ecr_assets import DockerImageAsset
from aws_cdk.aws_iam import CompositePrincipal
from aws_cdk.aws_lambda import Version
from constructs import Construct


class ListMonkStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        env: typing.Union[Environment, typing.Dict[str, typing.Any]],
        **kwargs,
    ) -> None:
        super().__init__(scope, id=id, env=env, **kwargs)

        self.dc_environment = self.node.try_get_context("dc-environment")
        self.account_id = env.account

        # Parameter store values
        self.ORIGIN_KEY = aws_ssm.StringParameter.from_string_parameter_name(
            self, "CloudFrontOriginToken", "/MailingList/CloudFrontOriginToken"
        ).string_value

        self.CERT_ARN = aws_ssm.StringParameter.from_string_parameter_name(
            self, "CertificateArn", "/MailingList/CertificateArn"
        ).string_value

        self.MEDIA_BUCKET_NAME = aws_ssm.StringParameter.from_string_parameter_name(
            self, "S3MediaBucketName", "/MailingList/S3MediaBucketName"
        ).string_value

        self.LISTMONK_DB_HOST = aws_ssm.StringParameter.from_string_parameter_name(
            self, "LISTMONK_db__host", "/MailingList/LISTMONK_db__host"
        ).string_value
        self.LISTMONK_DB_PASSWORD = aws_ssm.StringParameter.from_string_parameter_name(
            self,
            "LISTMONK_db__password",
            "/MailingList/LISTMONK_db__password",
        ).string_value
        self.LISTMONK_API_KEY = aws_ssm.StringParameter.from_string_parameter_name(
            self,
            "ListMonkApiKey",
            "/MailingList/ListMonkApiKey",
        ).string_value
        self.LISTMONK_DB_USER = aws_ssm.StringParameter.from_string_parameter_name(
            self, "LISTMONK_db__user", "/MailingList/LISTMONK_db__user"
        ).string_value

        # The first part of this should work, but a CDK bug means we can't look
        # up hosted zones with an SSM placeholder. Use boto to get it.
        # self.FQDN = aws_ssm.StringParameter.from_string_parameter_name(
        #     self, "ListMonkFQDN", "/MailingList/ListMonkFQDN"
        # ).string_value
        ssm_client = boto3.client("ssm")
        self.FQDN = ssm_client.get_parameter(Name="/MailingList/ListMonkFQDN")[
            "Parameter"
        ]["Value"]

        self.EVENT_BUS_ORG_PATHS = ssm_client.get_parameter(
            Name="/MailingList/EventBusOrgPaths"
        )["Parameter"]["Value"]

        us_ssm_client = boto3.client("ssm", region_name="us-east-1")
        self.CONGITO_FUNCTION_ARN = us_ssm_client.get_parameter(
            Name="/MailingList/CognitoFunctionArn"
        )["Parameter"]["Value"]

        self.app_function = self.make_listmonk()
        self.cloudfront = self.make_cloudfront()
        self.make_event_bus()
        self.make_onboarder()

    def make_listmonk(self):
        s3_bucket_policy = aws_iam.PolicyDocument(
            statements=[
                aws_iam.PolicyStatement(
                    resources=[f"arn:aws:s3:::{self.MEDIA_BUCKET_NAME}"],
                    actions=["s3:*"],
                )
            ],
        )
        listmonk_role = aws_iam.Role(
            self,
            "listmonk_policy",
            inline_policies={"S3Access": s3_bucket_policy},
            assumed_by=aws_iam.CompositePrincipal(
                aws_iam.ServicePrincipal("ecs.amazonaws.com"),
                aws_iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            ),
        )

        listmonk_asset = DockerImageAsset(
            self, "listmonk", directory="./app", file="Dockerfile"
        )

        cluster = aws_ecs.Cluster(self, "ListmonkCluster")

        self.alb = aws_ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "listmonk_fargate",
            cluster=cluster,
            task_image_options=aws_ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=aws_ecs.ContainerImage.from_docker_image_asset(listmonk_asset),
                container_port=8000,
                environment={
                    "LISTMONK_db__host": self.LISTMONK_DB_HOST,
                    "LISTMONK_db__password": self.LISTMONK_DB_PASSWORD,
                    "LISTMONK_db__user": self.LISTMONK_DB_USER,
                    "LISTMONK_db__port": "5432",
                },
            ),
            public_load_balancer=True,
        )
        listener: elbv2.ApplicationListener = self.alb.listener
        elbv2.ApplicationListenerRule(
            self,
            "origin_key_rule",
            priority=1,
            listener=listener,
            conditions=[
                elbv2.ListenerCondition.http_header(
                    name="origin_key", values=[self.ORIGIN_KEY]
                )
            ],
            action=elbv2.ListenerAction.forward([self.alb.target_group]),
        )
        elbv2.ApplicationListenerRule(
            self,
            "block_other_access",
            priority=2,
            listener=listener,
            conditions=[elbv2.ListenerCondition.path_patterns(["*"])],
            action=elbv2.ListenerAction.fixed_response(status_code=403),
        )

    def make_cloudfront(self):
        cert = aws_certificatemanager.Certificate.from_certificate_arn(
            self,
            "CertArn",
            certificate_arn=self.CERT_ARN,
        )

        alb_origin = aws_cloudfront_origins.LoadBalancerV2Origin(
            self.alb.load_balancer,
            custom_headers={"origin_key": self.ORIGIN_KEY},
            protocol_policy=aws_cloudfront.OriginProtocolPolicy.HTTP_ONLY,
        )

        cognito_function = Version.from_version_arn(
            self, "cognito_function", version_arn=self.CONGITO_FUNCTION_ARN
        )
        distribution = aws_cloudfront.Distribution(
            self,
            "ListMonkCloudFront",
            certificate=cert,
            domain_names=[self.FQDN],
            default_behavior=aws_cloudfront.BehaviorOptions(
                origin=alb_origin,
                allowed_methods=aws_cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=aws_cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=aws_cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                edge_lambdas=[
                    EdgeLambda(
                        event_type=aws_cloudfront.LambdaEdgeEventType.VIEWER_REQUEST,
                        function_version=cognito_function,
                    )
                ],
            ),
        )

        hosted_zone = aws_route53.HostedZone.from_lookup(
            self,
            "ListmonkDomain_id",
            domain_name=self.FQDN,
        )

        aws_route53.ARecord(
            self,
            "FQDN_A_RECORD_TO_CF",
            zone=hosted_zone,
            record_name=self.FQDN,
            target=aws_route53.RecordTarget.from_alias(
                aws_route53_targets.CloudFrontTarget(distribution)
            ),
        )

    def make_event_bus(self):
        self.event_bus = aws_events.EventBus(
            self, "event_bus", event_bus_name=f"MailingListEvents-{self.dc_environment}"
        )

        cross_account_policy = aws_iam.PolicyStatement(
            principals=[
                aws_iam.PrincipalWithConditions(
                    aws_iam.OrganizationPrincipal(
                        self.EVENT_BUS_ORG_PATHS.split("/")[0]
                    ),
                    conditions={
                        "ForAnyValue:StringLike": {
                            "aws:PrincipalOrgPaths": self.EVENT_BUS_ORG_PATHS.split(
                                ","
                            ),
                        },
                    },
                )
            ],
            sid=f"cross-org-mailinglist-event-bus-{self.dc_environment}",
            actions=["events:PutEvents"],
            resources=[self.event_bus.event_bus_arn],
        )

        self.event_bus.add_to_resource_policy(cross_account_policy)

        event_receiver_lambder = aws_lambda_python_alpha.PythonFunction(
            self,
            "mailing_list_event_receiver",
            entry="cdk/functions/mailinglist_events",
            runtime=aws_lambda.Runtime.PYTHON_3_10,
            index="handler.py",
            environment={
                "MAILINGLIST_API_KEY": self.LISTMONK_API_KEY,
                "FQDN": self.FQDN,
                "EVENT_BRIDGE_ARN": self.event_bus.event_bus_arn
            },
        )

        aws_events.Rule(
            self,
            "lambda_rule",
            event_bus=self.event_bus,
            event_pattern=aws_events.EventPattern(
                detail_type=["new_subscription", "first_welcome_email"]
            ),
        ).add_target(aws_events_targets.LambdaFunction(event_receiver_lambder))

    def make_onboarder(self):
        target_role = aws_iam.Role(
            self,
            "event_runner_role",
            inline_policies={
                "put-events": aws_iam.PolicyDocument(
                    statements=[
                        aws_iam.PolicyStatement(
                            actions=[
                                "events:PutEvents",
                            ],
                            resources=[self.event_bus.event_bus_arn],
                        )
                    ]
                )
            },
            assumed_by=aws_iam.ServicePrincipal("events.amazonaws.com"),
        )

        onboarder = aws_lambda_python_alpha.PythonFunction(
            self,
            "mailing_list_onboarder",
            entry="cdk/functions/onboard_scheduler",
            runtime=aws_lambda.Runtime.PYTHON_3_10,
            index="handler.py",
            environment={
                "MAILINGLIST_API_KEY": self.LISTMONK_API_KEY,
                "FQDN": self.FQDN,
                "EVENT_BUS_ARN": self.event_bus.event_bus_arn,
                "EVENT_BUS_ROLE_ARN": target_role.role_arn,
            },
        )
        onboarder.add_to_role_policy(
            statement=aws_iam.PolicyStatement(
                actions=[
                    "iam:PassRole",
                    "scheduler:CreateSchedule",
                ],
                resources=[
                    "*",
                ],
            )
        )
        onboarder_lambda_target = aws_events_targets.LambdaFunction(handler=onboarder)

        aws_events.Rule(
            self,
            "onboarder-schedule",
            schedule=aws_events.Schedule.rate(Duration.hours(1)),
            targets=[onboarder_lambda_target],
        )
