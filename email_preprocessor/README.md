# Email pre-processing

## Why this exists

Emails are tricky things to style. CSS doesn't really work in the same way that is does for browsers.

For example, in a browser you can do this:

```
<style>
a { color: red; }
</style>
<a href="#">Link</a>

```

There's a reasonable chance that the link will be red when you open it in a browser.

However, there's a much lower chance this will be the case in an email. 

To style a link in an email you need to do something like:

```
<a href="#" style="color: red;">Link</a>
```

The scripts in this directory convert the former to the latter.

## Installing

`gem install --user bootstrap-email`

(This requires Ruby to be installed)

[Install Pandoc](https://pandoc.org/installing.html)

## Using

1. Write the email using Markdown
2. Add the content to `email.md`
3. run `make all`
4. The file `final_output.html` contains the email

When adding to ListMonk, don't select a template. Just use the raw HTML option
