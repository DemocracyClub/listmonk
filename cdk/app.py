#!/usr/bin/env python3

import os

from aws_cdk import App, Environment, Tags
from stacks.edge_lambdas import LambdaAtEdgeStack
from stacks.listmonk_stack import ListMonkStack

valid_environments = (
    "development",
    "production",
)

app_wide_context = {}
if dc_env := os.environ.get("DC_ENVIRONMENT"):
    app_wide_context["dc-environment"] = dc_env

app = App(context=app_wide_context)

env = Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region="eu-west-2")
us_east_1_env = Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"), region="us-east-1"
)

# Set the DC Environment early on. This is important to be able to conditionally
# change the stack configurations
dc_environment = app.node.try_get_context("dc-environment") or None
assert (
    dc_environment in valid_environments
), f"context `dc-environment` must be one of {valid_environments}"

if not os.environ.get("LOCAL_API"):
    edge_lambbda = LambdaAtEdgeStack(
        app,
        "LambdaAtEdgeStack",
        env=us_east_1_env,
    )


list_monk = ListMonkStack(
    app,
    "ListMonkStack",
    env=env,
)


Tags.of(app).add("dc-product", "mailing-list")
Tags.of(app).add("dc-environment", dc_environment)

app.synth()
