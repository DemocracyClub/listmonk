import contextlib
import re
import shutil
import tempfile
import typing
from pathlib import Path
from string import Template

import boto3
from aws_cdk import (
    Duration,
    Environment,
    Stack,
    aws_iam,
    aws_lambda,
    aws_lambda_nodejs,
    aws_ssm,
)
from constructs import Construct

FUNCTION_SOURCE = Path("cdk/functions/node_cognito")
SSM_PREFIX = "/MailingList/"


class SSMTemplate(Template):
    delimiter = "$SSM$"


def replace_ssm_tokens(js_content):
    template = SSMTemplate(js_content)
    params = re.findall(r"\$SSM\$([a-zA-Z]+)", js_content)
    ssm_client = boto3.client("ssm", region_name="eu-west-2")
    vars = {}
    for param in params:
        print(param)
        param_key = f"{SSM_PREFIX}{param}"
        value = ssm_client.get_parameter(Name=param_key)["Parameter"]["Value"]
        vars[f"{param}"] = value
    return template.substitute(**vars)


@contextlib.contextmanager
def pre_process_js():
    """
    We can't just use SSM vars to add secrets at runtime for complex reasons:

    1. SSM requires a async call.
    2. await can only be run at the top level when running as an esmodule
    3. esmodules / edbuilt can't build dynamic `require()`
    4.`JWT` uses dynamic require() to get `crypto` https://github.com/evanw/esbuild/issues/1944
    5. This might be possible by playing with esbuild, but at that point
       the below method seemed to make more sense as the SSM values don't
       change between deploys.
    6. We want top level vars to save SSM being called on *every* invocation
    7. Baking them in also avoids them being called on every cold start.

    """
    temp_dir = Path(tempfile.mkdtemp())
    dest = temp_dir / "function"

    try:
        shutil.copytree(FUNCTION_SOURCE, dest)
        handler_path = dest / "handler.js"
        with handler_path.open() as handler_file:
            updated_file = replace_ssm_tokens(handler_file.read())
        with handler_path.open("w") as handler_file:
            handler_file.write(updated_file)

        yield dest

    finally:
        shutil.rmtree(temp_dir)


class LambdaAtEdgeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        env: typing.Union[Environment, typing.Dict[str, typing.Any]],
        **kwargs,
    ) -> None:
        super().__init__(scope, id=id, env=env, **kwargs)

        ssm_read_policy = aws_iam.PolicyDocument(
            statements=[
                aws_iam.PolicyStatement(
                    resources=["*"], actions=["ssm:GetParameter"]
                )
            ],
        )

        lambda_role = aws_iam.Role(
            self,
            "lambda_redirect_role",
            assumed_by=aws_iam.CompositePrincipal(
                aws_iam.ServicePrincipal("edgelambda.amazonaws.com"),
                aws_iam.ServicePrincipal("lambda.amazonaws.com"),
            ),
            inline_policies={"SSMAccess": ssm_read_policy},
        )
        lambda_role.add_managed_policy(
            aws_iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )
        with pre_process_js() as dest:
            self.cognito_lambda = aws_lambda_nodejs.NodejsFunction(
                self,
                "cognito_auth",
                function_name="cognito_at_edge_auth-node-function",
                entry=f"{dest}/handler.js",
                handler="handler",
                runtime=aws_lambda.Runtime.NODEJS_18_X,
                timeout=Duration.seconds(5),
                memory_size=128,
                role=lambda_role,
                aws_sdk_connection_reuse=False,
            )

        aws_ssm.StringParameter(
            self,
            "cognito_function_current_version",
            parameter_name="/MailingList/CognitoFunctionArn",
            string_value=self.cognito_lambda.current_version.function_arn,
        )
