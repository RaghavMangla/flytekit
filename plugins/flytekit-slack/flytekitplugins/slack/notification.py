from dataclasses import dataclass

from slack_sdk import WebClient

import flytekit
from flytekit.loggers import logger

from flytekit.core.base_notifier import BaseNotifier


@dataclass
class SlackConfig(object):
    channel: str
    secret_group: str
    secret_key: str


class SlackNotifier(BaseNotifier):
    def __init__(self, slack_conf: SlackConfig):
        self.slack_conf = slack_conf

    def send_notification(self, message: str):
        try:
            token = self.get_notification_secret()
            client = WebClient(token=token)
            client.chat_postMessage(channel=self.slack_conf.channel, text=message)

            logger.info("Slack notification sent successfully!")
        except Exception as e:
            logger.error(
                f"Failed to send slack notification, please check the variable in the slack_conf and the slack-api token.\n\
                    Error: {e}"
            )

    def get_notification_secret(self) -> str:
        return flytekit.current_context().secrets.get(self.slack_conf.secret_group, self.slack_conf.secret_key)
