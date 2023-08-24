import { Authenticator } from 'cognito-at-edge';

// These values are replaced at CDK synth time
// by requesting the values from SSM. (search `pre_process_js`)
// Getting the values from SSM at runtime ended up
// being too complex due to...something about
// ES Modules.
// For future, see https://aws.amazon.com/blogs/compute/using-node-js-es-modules-and-top-level-await-in-aws-lambda/
// and https://github.com/evanw/esbuild/issues/1944
const userPoolId = "$SSM$userPoolId";
const userPoolAppId = "$SSM$userPoolAppId";
const userPoolDomain = "$SSM$userPoolDomain";
const userPoolAppSecret = "$SSM$userPoolAppSecret";
const ListMonkApiKey = "$SSM$ListMonkApiKey";

const authenticator = new Authenticator({
    // Replace these parameter values with those of your own environment
    region: 'eu-west-2', // user pool region
    userPoolId: userPoolId, // user pool ID
    userPoolAppId: userPoolAppId, // user pool app client ID
    userPoolDomain: userPoolDomain, // user pool domain
    userPoolAppSecret: userPoolAppSecret,
    parseAuthPath: "/authLogin",
    logoutUri: "/authLogout",
    logLevel: "debug",
    cookieExpirationDays: 1,
    expirationDays: 1,
});

export async function handler(event) {
    'use strict';


    const { request } = event.Records[0].cf;
    if (request.uri === "/favicon.ico") {
        return request;
    }


    if (request.uri.startsWith('/authLogout')) {
        return authenticator.handleSignOut(event);
    }

    if (request.uri.startsWith('/authLogin')) {
        return authenticator.handleParseAuth(event);
    }

    if (
        request.uri.startsWith('/webhooks') ||
        request.uri.startsWith('/admin') ||
        request.uri.startsWith('/api')
    ) {

        var original_authorization;
        try {
            original_authorization = request.headers.authorization[0].value;
        } catch (error) {
            original_authorization = "";
        }

        request.headers.authorization = [
            {
                key: "Authorization",
                value: "Basic bGlzdG1vbms6bGlzdG1vbms="
            }
        ];

        if (original_authorization === ListMonkApiKey) {
            return request;
        }

        if (request.querystring.indexOf(ListMonkApiKey) !== -1) {
            return request;
        }

        return authenticator.handle(event);

    }

    return request;
};
