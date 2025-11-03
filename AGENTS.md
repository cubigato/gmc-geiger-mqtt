Write tests but don't overuse them.
When asked to write web code you can use puppeteer to verify the UI, but don't overuse it as it uses a lot of resources.
When changing something that changes what the software does or how it works make sure to update documentation and tests.

for python we use a venv in .venv. For python package management we use "uv". But NEVER install anything without asking the user for approval. You can update requirements.txt and tell the user how he can apply the changes with uv.
