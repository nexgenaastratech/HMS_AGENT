from app.services.hms import login_and_get_token
import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

print("Testing HMS login...")
token = login_and_get_token()
print(f"Resulting token: {token}")
