# DC Mailing list

This deploys [listmonk](https://listmonk.app/) to AWS and contains 
configuration files to make it look good.

The app itself is deployed to AWS Lambda using a Docker Container.

The container communicates over HTTP, and this is translated to a Lambda 
handler using [`aws-lambda-adapter`](https://github.com/awslabs/aws-lambda-web-adapter)

AWS SAM is used to wrap everything up and deploy it.

## Frontend and HTML templates

The application frontend is styled to look like DC's other products.

This is done according to the [listmonk templating docs](https://listmonk.app/docs/templating/).

The design system is implemented using a Makefile to write to the static 
directory. 

To make the design system and update the CSS, run `make static` from the 
root folder. `sass` needs to be on your `PATH` for this to work, best 
installed with `npm install -g sass`.

_Listmonk_ manages the email templates via the frontend / database. 

In order to keep these templates in source control, we have checked them in to 
`app_assets`. 

You need to login to the admin interface and copy/paste the contents of 
these files into the 'templates' section under campaigns. 

Of course, it's possible to just update the templates in the admin interface, 
however it's much better to do the work locally first and copy the finished 
template to the production environment.

## Local testing

You should only need to run locally to change the templates / theme.

If this is the first time running locally:

Download `listmonk` as per https://listmonk.app/#download

Run `listmonk --new-config`
Edit `config.yaml` with your DB setting.
Run `listmonk --install`
Run `listmonk --static-dir=app/static`
Visit http://localhost:3000

## Deploying

1. Log in to the AWS SSO account you want to deploy to
2. `export DC_ENVIRONMENT=` according to the environment you're deploying to
3. run `make deploy`


## New environment install

### Set up the DNS and cert

1. Make sure you have a hosted one for your domain name in the account you're 
using and the hosted zone is 'live' (the DNS is pointed to it).
2. Create an ACM cert _in the us-west-1 location_ and verify it
3. Grab the ARN of the cert and add it to the parameter store (see below)


### Make an S3 media bucket and IAM user

We need to give ListMonk an IAM user for uploading media
(it doesn't support role based authentication).


In the S3 console, make a new bucket [bucket_name] and ensure that public 
access _is not blocked. Also allow ACLs under object ownership.

In the AWS account you're using, create a new IAM user (the name doesn't matter)
and give it the following inline policy:

```json
{
	"Version": "2012-10-17",
	"Statement": [
		{
			"Sid": "Statement1",
			"Effect": "Allow",
			"Action": ["s3:*"],
			"Resource": [
              "arn:aws:s3:::[bucket_name]",
              "arn:aws:s3:::[bucket_name]/*"
            ]
		}
	]
}
```

Create new access keys for the user, ignoring the wanings about using role 
based auth. 

Make a note of the Access key and Secret access key for later.


### Parameter Store keys

* `/MailingList/S3MediaBucketName` Media bucket name (as above)
* `/MailingList/ListMonkFQDN` Domain name
* `/MailingList/CertificateArn` ACM ARN (as above) 
* `/MailingList/CloudFrontOriginToken` A private token to prevent direct 
  access to API Gateway. Set to something long and unguessable
* `/MailingList/ListMonkApiKey` The token the Lambda functions use to
  authenticate against `https://{ListMonkFQDN}/api/`. Create an API user called
  `lambda_key` in ListMonk's admin UI (the name is set by `LISTMONK_API_USER` 
  in `cdk/stacks/listmonk_stack.py`), with a user role that has the 
  `lists:get_all`, `lists:manage_all`, `subscribers:get_all`, 
  `subscribers:manage`, `subscribers:sql_query` and `tx:send` permissions, and 
  use its token as the value
* `/MailingList/LISTMONK_db__host` The RDS host
* `/MailingList/LISTMONK_db__user` The RDS user
* `/MailingList/LISTMONK_db__password` The RDS password
* `/MailingList/AlertEmail` The address to email when sign ups are failing. 
  AWS sends a confirmation link to this address after the first deploy, and 
  no alerts arrive until it has been clicked

## Failed sign ups

Sign up and welcome email events that can't be processed go to a dead letter 
queue, after Lambda has retried them twice. An email is sent to 
`/MailingList/AlertEmail` when the queue stops being empty. 

The alarm stays on while there are messages in the queue, so further failures 
won't send another email until it has been cleared. Messages are deleted after 
14 days, so anything still there needs replaying before then.

To replay a message, fix the problem and then invoke the event receiver Lambda 
with the message body as its payload. Once it has succeeded, delete the message 
from the queue.

The same address is emailed if the hourly onboarder Lambda fails. This doesn't 
use the queue, as the next run retries anyone who signed up in the last 24 
hours. Check the function's logs, as anyone older than that isn't retried.
