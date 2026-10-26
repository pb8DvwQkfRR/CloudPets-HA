"""Constants for the CloudPets integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "cloudpets"

API_BASE: Final = "https://cn.cloudpets.net/app"
REQUEST_TIMEOUT: Final = 15
DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=300)

CONF_ACCOUNT: Final = "account"
CONF_PASSWORD: Final = "password"
CONF_SCAN_INTERVAL: Final = "scan_interval"

MANUFACTURER: Final = "CloudPets"
MODEL_UNKNOWN: Final = "智能喂食器"

ATTR_DEVICE_ID: Final = "device_id"
ATTR_NAME: Final = "name"
ATTR_TIME: Final = "time"
ATTR_SERVINGS: Final = "servings"
ATTR_ENABLED: Final = "enabled"
ATTR_DAYS: Final = "days"
ATTR_PLAN_ID: Final = "plan_id"

SERVICE_CREATE_FEED_PLAN: Final = "create_feed_plan"
SERVICE_UPDATE_FEED_PLAN: Final = "update_feed_plan"
SERVICE_DELETE_FEED_PLAN: Final = "delete_feed_plan"

PLATFORMS: Final = [
    "binary_sensor",
    "button",
    "number",
    "sensor",
    "switch",
    "time",
]
